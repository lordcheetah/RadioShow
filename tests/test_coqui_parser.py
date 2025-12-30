# tests/test_coqui_parser.py
from tts_engines import CoquiXTTS

SAMPLES = [
    ("Epoch: 1/5, Step: 10/100, loss: 0.1234, ETA: 00:20", {'epoch':1,'epoch_total':5,'step':10,'step_total':100,'loss':0.1234}),
    ("Train: [10/100 (10%)]\tLoss: 0.1234", {'step':10,'step_total':100,'percent':10.0,'loss':0.1234}),
    ("Epoch 2/10 [20/200] 10% |████| 00:05<00:20, 4.00it/s", {'epoch':2,'epoch_total':10,'step':20,'step_total':200,'percent':10.0}),
    ("INFO - Epoch: 3/50 - loss: 0.4567 - ETA: 00:30", {'epoch':3,'epoch_total':50,'loss':0.4567})
]

parser = CoquiXTTS(None, None)._parse_trainer_output


def test_parser_samples():
    for line, expected in SAMPLES:
        parsed = parser(line)
        assert parsed is not None, f"Parser returned None for: {line}"
        for k, v in expected.items():
            assert k in parsed, f"Expected key '{k}' missing in parsed output for line: {line}. Parsed: {parsed}"
            # Only check numeric closeness for floats
            if isinstance(v, float):
                assert abs(parsed[k] - v) < 1e-6, f"Value mismatch for key {k}: {parsed[k]} != {v}"
            else:
                assert parsed[k] == v, f"Value mismatch for key {k}: {parsed[k]} != {v}"


if __name__ == '__main__':
    test_parser_samples()
    print('All parser sample tests passed')
