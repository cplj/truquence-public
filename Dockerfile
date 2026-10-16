FROM python:3.12.15-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/opt/app
RUN python -c "import pathlib, shutil, sysconfig; lib = pathlib.Path(sysconfig.get_path('purelib')); targets = [*lib.glob('pip*'), *lib.glob('setuptools*'), *lib.glob('wheel*'), lib / 'pkg_resources', pathlib.Path(sysconfig.get_path('stdlib')) / 'ensurepip']; [(shutil.rmtree(p) if p.is_dir() else p.unlink()) for p in targets if p.exists()]; [(p.unlink()) for p in pathlib.Path('/usr/local/bin').glob('pip*') if p.is_file()]"
COPY LICENSE NOTICE /usr/share/doc/truquence/
COPY src /opt/app
RUN python -c "from pathlib import Path; p = Path('/usr/local/bin/truquence'); p.write_text('#!/usr/local/bin/python\nfrom truquence.entry import main\nraise SystemExit(main())\n'); p.chmod(0o755)"
WORKDIR /work
RUN python -c "import os; os.chown('/work', 65532, 65532)"
USER 65532:65532
ENTRYPOINT ["truquence"]
CMD ["--help"]
