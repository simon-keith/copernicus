import re

import pytest

from copernicus.evalscripts import Evalscript
from copernicus.evalscripts import ScriptKind


@pytest.mark.parametrize("script", list(Evalscript))
class TestEvalscripts:
    def test_is_a_v3_script(self, script):
        source = script.source()
        assert source.startswith("//VERSION=3")
        assert "function setup()" in source
        assert "function evaluatePixel(" in source

    def test_declares_exactly_the_expected_inputs(self, script):
        declared = re.findall(
            r'datasource:\s*"(\w+)"',
            script.source(),
        )
        assert sorted(declared) == sorted(script.inputs)

    def test_only_numeric_scripts_return_float32(self, script):
        is_float = 'sampleType: "FLOAT32"' in script.source()
        assert is_float == (script.kind is not ScriptKind.IMAGE)

    def test_statistics_scripts_output_a_data_mask(self, script):
        has_mask_output = 'id: "dataMask"' in script.source()
        assert has_mask_output == (script.kind is ScriptKind.STATISTICS)
