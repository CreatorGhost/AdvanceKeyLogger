"""Secure string wrapper that prevents accidental exposure of sensitive values.

Inspired by Pydantic's ``SecretStr`` pattern, :class:`SecureString` makes it
impossible to accidentally log, print, or serialise the real value — you must
call :meth:`reveal` (or :meth:`get_secret_value`) explicitly.

Usage::

    from utils.secure_string import SecureString

    secret = SecureString.from_plain("hunter2")
    print(secret)            # ***
    repr(secret)             # SecureString('***')
    secret.reveal()          # 'hunter2'
    len(secret)              # 7
    bool(secret)             # True
"""
from __future__ import annotations


class SecureString:
    """Wraps a string so its value is hidden from ``repr`` / ``str`` / logging.

    The only way to obtain the real value is via :meth:`reveal` (or the
    :meth:`get_secret_value` alias provided for Pydantic compatibility).

    This class is safe to use as a ``dataclass`` field type.
    """

    __slots__ = ("_value",)

    def __init__(self, value: str) -> None:
        self._value = value

    # ── Factory ───────────────────────────────────────────────────────

    @classmethod
    def from_plain(cls, value: str) -> SecureString:
        """Create a :class:`SecureString` from a plain-text string."""
        return cls(value)

    # ── Access ────────────────────────────────────────────────────────

    def reveal(self) -> str:
        """Return the actual secret value."""
        return self._value

    def get_secret_value(self) -> str:
        """Alias for :meth:`reveal` (Pydantic ``SecretStr`` compatibility)."""
        return self._value

    # ── Representation (always masked) ────────────────────────────────

    def __repr__(self) -> str:  # noqa: D105
        return "SecureString('***')"

    def __str__(self) -> str:  # noqa: D105
        return "***"

    # ── Comparison / boolean / length ─────────────────────────────────

    def __eq__(self, other: object) -> bool:  # noqa: D105
        if isinstance(other, SecureString):
            return self._value == other._value
        return NotImplemented

    def __hash__(self) -> int:  # noqa: D105
        return hash(self._value)

    def __bool__(self) -> bool:  # noqa: D105
        return bool(self._value)

    def __len__(self) -> int:  # noqa: D105
        return len(self._value)

    # ── Dataclass / copy support ──────────────────────────────────────

    def __reduce__(self) -> tuple[type, tuple[str]]:
        """Support pickling (needed for ``copy.deepcopy`` in some dataclass ops)."""
        return (self.__class__, (self._value,))
