import re

import pytest

from copernicus.evalscripts import Evalscript
from copernicus.evalscripts import ScriptKind


def filled(script: Evalscript) -> str:
    return script.source(**dict.fromkeys(script.parameters, 0.0))


@pytest.mark.parametrize("script", list(Evalscript))
class TestEvalscripts:
    def test_is_a_v3_script(self, script):
        source = filled(script)
        assert source.startswith("//VERSION=3")
        assert "function setup()" in source
        assert "function evaluatePixel(" in source

    def test_declares_exactly_the_expected_inputs(self, script):
        declared = re.findall(
            r'datasource:\s*"(\w+)"',
            filled(script),
        )
        assert sorted(declared) == sorted(script.inputs)

    def test_only_numeric_scripts_return_float32(self, script):
        is_float = 'sampleType: "FLOAT32"' in script.source(
            **dict.fromkeys(script.parameters, 0.0)
        )
        assert is_float == (script.kind is not ScriptKind.IMAGE)

    def test_statistics_scripts_output_a_data_mask(self, script):
        has_mask_output = 'id: "dataMask"' in script.source(
            **dict.fromkeys(script.parameters, 0.0)
        )
        assert has_mask_output == (script.kind is ScriptKind.STATISTICS)


class TestParameters:
    def test_fills_every_placeholder(self):
        text = Evalscript.LARCH_DELTA.source(CONTROL_PSRI=-0.0125)
        assert "__" not in text
        assert "var CONTROL_PSRI = -0.0125;" in text

    def test_rejects_unknown_parameters(self):
        with pytest.raises(ValueError, match="needs parameters"):
            Evalscript.TRUE_COLOR.source(CONTROL_PSRI=0.1)
