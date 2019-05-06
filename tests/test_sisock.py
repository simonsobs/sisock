import sisock

def test_sisock_uri():
    assert sisock.base.uri('test') == 'org.simonsobservatory.test'
