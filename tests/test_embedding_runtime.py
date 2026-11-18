from types import SimpleNamespace

import pytest

from almonium_book_processor.processing import nlp


def fake_torch(*, cuda=False, cuda_bf16=False, mps=False, avx512_bf16=False):
    return SimpleNamespace(
        cuda=SimpleNamespace(is_available=lambda: cuda, is_bf16_supported=lambda: cuda_bf16),
        backends=SimpleNamespace(mps=SimpleNamespace(is_available=lambda: mps)),
        cpu=SimpleNamespace(
            _is_avx512_bf16_supported=lambda: avx512_bf16, _is_amx_tile_supported=lambda: False
        ),
    )


@pytest.fixture
def x86(monkeypatch):
    monkeypatch.setattr("platform.machine", lambda: "x86_64")


def test_a_gpu_is_used_when_one_is_visible_in_the_precision_it_does_natively(x86):
    newer = nlp._resolve_runtime(fake_torch(cuda=True, cuda_bf16=True), "auto", "auto", 0)
    older = nlp._resolve_runtime(fake_torch(cuda=True), "auto", "auto", 0)
    assert (newer.device, newer.precision, newer.batch_size) == ("cuda", "bf16", 128)
    assert (older.device, older.precision) == ("cuda", "fp16")


def test_a_cpu_reduces_precision_only_where_it_multiplies_in_bf16(x86):
    native = nlp._resolve_runtime(fake_torch(avx512_bf16=True), "auto", "auto", 0)
    emulated = nlp._resolve_runtime(fake_torch(), "auto", "auto", 0)
    assert (native.device, native.precision, native.batch_size) == ("cpu", "bf16", 32)
    assert emulated.precision == "fp32"


def test_an_arm_cpu_reads_bf16_from_its_feature_flags(monkeypatch, tmp_path):
    monkeypatch.setattr("platform.machine", lambda: "aarch64")
    cpuinfo = tmp_path / "cpuinfo"
    real_open = open

    def opener(path, *args, **kwargs):
        return real_open(cpuinfo if path == "/proc/cpuinfo" else path, *args, **kwargs)

    monkeypatch.setattr("builtins.open", opener)
    cpuinfo.write_text("Features\t: fp asimd evtstrm aes pmull sha1 sha2 crc32 atomics\n")
    assert nlp._resolve_runtime(fake_torch(), "auto", "auto", 0).precision == "fp32"
    cpuinfo.write_text("Features\t: fp asimd sve bf16 i8mm\n")
    assert nlp._resolve_runtime(fake_torch(), "auto", "auto", 0).precision == "bf16"


def test_settings_override_what_was_detected(x86):
    runtime = nlp._resolve_runtime(fake_torch(avx512_bf16=True), "cpu", "fp32", 16)
    assert (runtime.device, runtime.precision, runtime.batch_size) == ("cpu", "fp32", 16)
    with pytest.raises(ValueError, match="precision"):
        nlp._resolve_runtime(fake_torch(), "cpu", "int4", 0)
