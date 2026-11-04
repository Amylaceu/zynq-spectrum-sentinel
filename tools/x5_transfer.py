"""Bound SCP command lengths when retrieving many immutable X5 captures."""
from pathlib import PurePosixPath
import subprocess


def retrieval_commands(target, directory, names, destination, options=(), limit=24000):
    """Return explicit-file batches below Windows' 32767-character limit.

    No wildcard or shell interpolation is used. Keep headroom for the process
    launcher and bound each transfer to 64 files on both Windows and Linux.
    """
    names = list(names)
    if not names or len(set(names)) != len(names):
        raise ValueError('Require nonempty, unique capture filenames')
    if any(not name or PurePosixPath(name).name != name or
           name in ('.', '..') or '\\' in name for name in names):
        raise ValueError('Require plain capture filenames')
    prefix = ['scp', *options]
    commands, sources = [], []
    for name in names:
        source = target+':'+directory+'/'+name
        candidate = [*prefix, *sources, source, str(destination)]
        if sources and (len(sources) >= 64 or len(subprocess.list2cmdline(candidate)) >= limit):
            commands.append([*prefix, *sources, str(destination)])
            sources = []
        sources.append(source)
        if len(subprocess.list2cmdline([*prefix, *sources, str(destination)])) >= limit:
            raise ValueError('One capture path exceeds transfer command limit')
    commands.append([*prefix, *sources, str(destination)])
    return commands


def retrieve_files(target, directory, names, destination, options=()):
    for command in retrieval_commands(target, directory, names, destination, options):
        subprocess.run(command, check=True, timeout=180)
