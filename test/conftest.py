# Copyright 2024-2026 Cusp AI
# SPDX-License-Identifier: Apache-2.0

import contextlib
import io
import sys
import textwrap

import pytest

from nanoargs.cli import NanoArgs


@contextlib.contextmanager
def capture_stdio():
    old_out, old_err = sys.stdout, sys.stderr
    buf_out, buf_err = io.StringIO(), io.StringIO()
    try:
        sys.stdout, sys.stderr = buf_out, buf_err
        yield buf_out, buf_err
    finally:
        sys.stdout, sys.stderr = old_out, old_err


@pytest.fixture
def run_parse():
    def _run(model, argv):
        with capture_stdio() as (out, err):
            try:
                NanoArgs(model).parse(argv=argv)
            except SystemExit:
                pass
        return out.getvalue(), err.getvalue()

    return _run


@pytest.fixture
def write_file(tmp_path):
    def _write(path, content: str):
        p = path if isinstance(path, type(tmp_path)) else tmp_path / path
        p.write_text(textwrap.dedent(content))
        return p

    return _write
