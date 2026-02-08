"""Tests for utility modules: crypto, compression, system_info, process, resilience."""
from __future__ import annotations

import os
import time
import pytest
from pathlib import Path

from utils.crypto import (
    generate_key,
    key_to_base64,
    key_from_base64,
    derive_key_from_password,
    encrypt,
    decrypt,
)
from utils.compression import (
    zip_files,
    zip_data,
    unzip_data,
    gzip_data,
    gunzip_data,
)
from utils.system_info import get_system_info, get_platform
from utils.process import PIDLock, GracefulShutdown
from utils.resilience import retry, TransportQueue, CircuitBreaker


# ============================================================
# Crypto tests
# ============================================================


class TestCrypto:
    """Tests for encryption utilities."""

    def test_generate_key(self):
        """Generated key is 32 bytes (256 bits)."""
        key = generate_key()
        assert isinstance(key, bytes)
        assert len(key) == 32

    def test_generate_key_uniqueness(self):
        """Each generated key is unique."""
        keys = {generate_key() for _ in range(10)}
        assert len(keys) == 10

    def test_key_base64_roundtrip(self):
        """Key survives base64 encode/decode."""
        key = generate_key()
        encoded = key_to_base64(key)
        decoded = key_from_base64(encoded)
        assert decoded == key

    def test_encrypt_decrypt_roundtrip(self):
        """Data survives encrypt/decrypt cycle."""
        key = generate_key()
        plaintext = b"Hello, World! This is secret data."
        ciphertext = encrypt(plaintext, key)
        result = decrypt(ciphertext, key)
        assert result == plaintext

    def test_ciphertext_differs_from_plaintext(self):
        """Encrypted data is different from original."""
        key = generate_key()
        plaintext = b"secret"
        ciphertext = encrypt(plaintext, key)
        assert ciphertext != plaintext

    def test_different_iv_each_time(self):
        """Encrypting same data twice produces different ciphertext."""
        key = generate_key()
        plaintext = b"same data"
        c1 = encrypt(plaintext, key)
        c2 = encrypt(plaintext, key)
        assert c1 != c2

    def test_wrong_key_fails(self):
        """Decryption with wrong key fails."""
        key1 = generate_key()
        key2 = generate_key()
        ciphertext = encrypt(b"secret", key1)
        with pytest.raises(Exception):
            decrypt(ciphertext, key2)

    def test_derive_key_from_password(self):
        """Password derivation produces consistent keys with same salt."""
        key1, salt = derive_key_from_password("my-password")
        key2, _ = derive_key_from_password("my-password", salt=salt)
        assert key1 == key2
        assert len(key1) == 32

    def test_different_passwords_different_keys(self):
        """Different passwords produce different keys."""
        key1, salt = derive_key_from_password("password1")
        key2, _ = derive_key_from_password("password2", salt=salt)
        assert key1 != key2

    def test_decrypt_too_short(self):
        """Decrypting too-short data raises ValueError."""
        key = generate_key()
        with pytest.raises(ValueError, match="too short"):
            decrypt(b"short", key)

    def test_encrypt_empty_data(self):
        """Can encrypt and decrypt empty bytes."""
        key = generate_key()
        ciphertext = encrypt(b"", key)
        result = decrypt(ciphertext, key)
        assert result == b""

    def test_encrypt_large_data(self):
        """Can encrypt and decrypt large data."""
        key = generate_key()
        plaintext = os.urandom(10 * 1024)  # 10 KB
        ciphertext = encrypt(plaintext, key)
        result = decrypt(ciphertext, key)
        assert result == plaintext


# ============================================================
# Compression tests
# ============================================================


class TestCompression:
    """Tests for compression utilities."""

    def test_zip_files(self, tmp_path: Path):
        """zip_files compresses multiple files."""
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_text("Hello" * 100)
        f2.write_text("World" * 100)

        archive = zip_files([str(f1), str(f2)])
        assert isinstance(archive, bytes)
        assert len(archive) > 0
        assert len(archive) < f1.stat().st_size + f2.stat().st_size

    def test_zip_files_to_disk(self, tmp_path: Path):
        """zip_files can save to disk."""
        f1 = tmp_path / "data.txt"
        f1.write_text("content")
        output = tmp_path / "output.zip"
        zip_files([str(f1)], output_path=str(output))
        assert output.exists()

    def test_zip_files_missing_file(self, tmp_path: Path):
        """zip_files skips missing files."""
        f1 = tmp_path / "exists.txt"
        f1.write_text("data")
        archive = zip_files([str(f1), "/nonexistent/file.txt"])
        assert isinstance(archive, bytes)

    def test_zip_data_roundtrip(self):
        """Data survives zip/unzip cycle."""
        original = b"Hello, World!" * 100
        archive = zip_data(original, filename="test.bin")
        extracted = unzip_data(archive)
        assert extracted["test.bin"] == original

    def test_gzip_roundtrip(self):
        """Data survives gzip/gunzip cycle."""
        original = b"Repeated data " * 1000
        compressed = gzip_data(original)
        decompressed = gunzip_data(compressed)
        assert decompressed == original

    def test_gzip_actually_compresses(self):
        """gzip produces smaller output for compressible data."""
        original = b"AAAA" * 10000
        compressed = gzip_data(original)
        assert len(compressed) < len(original)

    def test_gzip_empty_data(self):
        """Can gzip/gunzip empty bytes."""
        compressed = gzip_data(b"")
        decompressed = gunzip_data(compressed)
        assert decompressed == b""


# ============================================================
# System info tests
# ============================================================


class TestSystemInfo:
    """Tests for system info utilities."""

    def test_get_system_info_keys(self):
        """get_system_info returns expected keys."""
        info = get_system_info()
        expected_keys = {
            "hostname", "username", "os", "os_version", "os_release",
            "architecture", "python_version", "local_ip", "timestamp", "pid",
        }
        assert expected_keys == set(info.keys())

    def test_get_system_info_types(self):
        """All values are strings."""
        info = get_system_info()
        for key, value in info.items():
            assert isinstance(value, str), f"{key} is {type(value)}, expected str"

    def test_get_platform(self):
        """get_platform returns a lowercase string."""
        plat = get_platform()
        assert plat in ("linux", "windows", "darwin")
        assert plat == plat.lower()


# ============================================================
# Process management tests
# ============================================================


class TestPIDLock:
    """Tests for PIDLock."""

    def test_acquire_and_release(self, tmp_path: Path):
        """Can acquire and release a PID lock."""
        lock = PIDLock(str(tmp_path / "test.pid"))
        assert lock.acquire() is True
        assert (tmp_path / "test.pid").exists()
        lock.release()
        assert not (tmp_path / "test.pid").exists()

    def test_double_acquire_same_pid(self, tmp_path: Path):
        """Second acquire from same process detects running instance."""
        lock1 = PIDLock(str(tmp_path / "test.pid"))
        assert lock1.acquire() is True
        lock2 = PIDLock(str(tmp_path / "test.pid"))
        assert lock2.acquire() is False
        lock1.release()

    def test_stale_pid_file(self, tmp_path: Path):
        """Stale PID file (dead process) is cleaned up."""
        pid_file = tmp_path / "test.pid"
        pid_file.write_text("99999999")  # Very unlikely to be a real PID
        lock = PIDLock(str(pid_file))
        assert lock.acquire() is True
        lock.release()

    def test_corrupt_pid_file(self, tmp_path: Path):
        """Corrupt PID file is handled gracefully."""
        pid_file = tmp_path / "test.pid"
        pid_file.write_text("not-a-number")
        lock = PIDLock(str(pid_file))
        assert lock.acquire() is True
        lock.release()


class TestGracefulShutdown:
    """Tests for GracefulShutdown."""

    def test_initial_state(self):
        """Shutdown is not requested initially."""
        shutdown = GracefulShutdown()
        assert shutdown.requested is False
        shutdown.restore()

    def test_restore_handlers(self):
        """restore() resets signal handlers."""
        shutdown = GracefulShutdown()
        shutdown.restore()
        # Should not raise


# ============================================================
# Resilience tests
# ============================================================


class TestRetry:
    """Tests for the retry decorator."""

    def test_succeeds_first_try(self):
        """Function that succeeds runs once."""
        call_count = 0

        @retry(max_attempts=3, backoff_base=0.01)
        def succeed():
            nonlocal call_count
            call_count += 1
            return "ok"

        assert succeed() == "ok"
        assert call_count == 1

    def test_retries_on_failure(self):
        """Function is retried on exception."""
        call_count = 0

        @retry(max_attempts=3, backoff_base=0.01)
        def fail_twice():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("fail")
            return "ok"

        assert fail_twice() == "ok"
        assert call_count == 3

    def test_raises_after_max_attempts(self):
        """Raises after exhausting all attempts."""

        @retry(max_attempts=2, backoff_base=0.01)
        def always_fail():
            raise ValueError("always fails")

        with pytest.raises(ValueError, match="always fails"):
            always_fail()

    def test_specific_exceptions(self):
        """Only retries on specified exception types."""
        call_count = 0

        @retry(max_attempts=3, backoff_base=0.01, exceptions=(ConnectionError,))
        def fail_with_type_error():
            nonlocal call_count
            call_count += 1
            raise TypeError("wrong type")

        with pytest.raises(TypeError):
            fail_with_type_error()
        assert call_count == 1  # No retry for TypeError

    def test_retry_on_false(self):
        """retry_on_false retries when function returns False."""
        call_count = 0

        @retry(max_attempts=3, backoff_base=0.01, retry_on_false=True)
        def fail_then_succeed():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                return False
            return True

        assert fail_then_succeed() is True
        assert call_count == 3

    def test_retry_on_false_exhausted(self):
        """retry_on_false returns False after all attempts exhausted."""
        call_count = 0

        @retry(max_attempts=2, backoff_base=0.01, retry_on_false=True)
        def always_false():
            nonlocal call_count
            call_count += 1
            return False

        assert always_false() is False
        assert call_count == 2


class TestTransportQueue:
    """Tests for TransportQueue."""

    def test_enqueue_and_drain(self):
        """Items can be enqueued and drained."""
        q = TransportQueue()
        q.enqueue({"data": "a"})
        q.enqueue({"data": "b"})
        batch = q.drain(10)
        assert len(batch) == 2
        assert batch[0]["data"] == "a"

    def test_drain_batch_size(self):
        """drain respects batch_size limit."""
        q = TransportQueue()
        for i in range(10):
            q.enqueue({"data": i})
        batch = q.drain(3)
        assert len(batch) == 3
        assert q.size == 7

    def test_requeue(self):
        """requeue puts items back at the front."""
        q = TransportQueue()
        q.enqueue({"data": "old"})
        batch = q.drain(10)
        q.enqueue({"data": "new"})
        q.requeue(batch)
        result = q.drain(10)
        assert result[0]["data"] == "old"
        assert result[1]["data"] == "new"

    def test_max_size(self):
        """Queue respects max_size, dropping oldest."""
        q = TransportQueue(max_size=3)
        for i in range(5):
            q.enqueue({"data": i})
        assert q.size == 3
        batch = q.drain(10)
        assert batch[0]["data"] == 2  # First two were dropped

    def test_is_empty(self):
        """is_empty returns correct state."""
        q = TransportQueue()
        assert q.is_empty is True
        q.enqueue({"data": "x"})
        assert q.is_empty is False

    def test_enqueue_many(self):
        """enqueue_many adds multiple items."""
        q = TransportQueue()
        q.enqueue_many([{"data": i} for i in range(5)])
        assert q.size == 5


class TestCircuitBreaker:
    """Tests for CircuitBreaker."""

    def test_initial_state_closed(self):
        """Circuit starts in CLOSED state."""
        cb = CircuitBreaker()
        assert cb.state == CircuitBreaker.CLOSED
        assert cb.can_proceed() is True

    def test_opens_after_threshold(self):
        """Circuit opens after failure_threshold failures."""
        cb = CircuitBreaker(failure_threshold=3, cooldown=60)
        for _ in range(3):
            cb.record_failure()
        assert cb.state == CircuitBreaker.OPEN
        assert cb.can_proceed() is False

    def test_success_resets_failures(self):
        """Success resets the failure counter."""
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitBreaker.CLOSED  # Not 3 consecutive

    def test_half_open_after_cooldown(self):
        """Circuit transitions to HALF_OPEN after cooldown."""
        cb = CircuitBreaker(failure_threshold=1, cooldown=0.05)
        cb.record_failure()
        assert cb.state == CircuitBreaker.OPEN
        time.sleep(0.1)
        assert cb.can_proceed() is True
        assert cb.state == CircuitBreaker.HALF_OPEN

    def test_half_open_to_closed_on_success(self):
        """Successful request in HALF_OPEN closes circuit."""
        cb = CircuitBreaker(failure_threshold=1, cooldown=0.01)
        cb.record_failure()
        time.sleep(0.02)
        cb.can_proceed()  # Transitions to HALF_OPEN
        cb.record_success()
        assert cb.state == CircuitBreaker.CLOSED

    def test_half_open_to_open_on_failure(self):
        """Failed request in HALF_OPEN re-opens circuit."""
        cb = CircuitBreaker(failure_threshold=1, cooldown=0.01)
        cb.record_failure()
        time.sleep(0.02)
        cb.can_proceed()  # HALF_OPEN
        cb.record_failure()
        assert cb.state == CircuitBreaker.OPEN
