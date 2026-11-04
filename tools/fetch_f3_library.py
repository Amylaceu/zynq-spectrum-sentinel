"""Retrieve the accepted board library without compiling or touching RF."""
from pathlib import Path

from x2_transport import ROOT, Transport, sha, verified, write_evidence


def main():
    record = verified(ROOT/'board/measurements/f3_library_r1.json')
    if record['status'] != 'PASS':
        raise ValueError('An accepted F3 library is required')
    remote = record['remote_root']+'/libad9361_f3.so'
    target = ROOT/'build/f3_library/libad9361_f3.so'
    expected = record['library_sha256']
    if target.exists():
        if sha(target) != expected:
            raise ValueError('Existing local library differs; preserve it for inspection')
        print('F3_LIBRARY_ALREADY_VERIFIED '+expected)
        return
    transport = Transport()
    if transport.ssh(['sha256sum', remote]).split()[0] != expected:
        raise ValueError('Board library differs from accepted build')
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix('.so.partial')
    if partial.exists():
        raise FileExistsError('Preserve prior incomplete library download')
    transport.copy(transport.target+':'+remote, partial)
    if sha(partial) != expected:
        raise ValueError('Transferred library checksum mismatch')
    partial.rename(target)
    Path(str(target)+'.sha256').write_text(expected+'  '+target.name+'\n', encoding='ascii')
    write_evidence(ROOT/'board/measurements/f3_library_retrieval.json', dict(
        status='PASS', source=remote, destination=target.relative_to(ROOT).as_posix(),
        sha256=expected, bytes=target.stat().st_size, rf_access=False,
        build_result_sha256=sha(ROOT/'board/measurements/f3_library_r1.json')))
    print('F3_LIBRARY_RETRIEVED_VERIFIED '+expected)


if __name__ == '__main__':
    main()
