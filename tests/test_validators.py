from pmm.runtime.validators import validate_bot_metrics


def test_validate_bot_metrics_matches():
    """Test that validator correctly identifies matching metrics."""
    metrics = {"IAS": 0.5, "GAS": 0.3}
    response = "System status: IAS=0.500, GAS=0.300"
    assert validate_bot_metrics(response, metrics)


def test_validate_bot_metrics_mismatch():
    """Test that validator correctly identifies mismatched metrics."""
    metrics = {"IAS": 0.5, "GAS": 0.3}
    response = "System status: IAS=0.900, GAS=0.000"
    assert not validate_bot_metrics(response, metrics)


def test_validate_bot_metrics_tolerance():
    """Test that validator uses tolerance correctly."""
    metrics = {"IAS": 0.5, "GAS": 0.3}
    # Should pass within tolerance (±0.01)
    response = "System status: IAS=0.505, GAS=0.295"
    assert validate_bot_metrics(response, metrics)

    # Should fail outside tolerance
    response = "System status: IAS=0.520, GAS=0.295"
    assert not validate_bot_metrics(response, metrics)


def test_validate_bot_metrics_no_numbers():
    """Test that validator returns True when no metrics are mentioned."""
    metrics = {"IAS": 0.5, "GAS": 0.3}
    response = "Hello world"  # no metrics in text
    assert validate_bot_metrics(response, metrics)


def test_validate_bot_metrics_malformed():
    """Test that validator handles malformed metric strings gracefully."""
    metrics = {"IAS": 0.5, "GAS": 0.3}
    response = "System status: IAS=abc, GAS=0.300"  # invalid IAS
    assert validate_bot_metrics(response, metrics)  # should return True due to no match

    response = "System status: IAS=0.500, GAS=def"  # invalid GAS
    assert validate_bot_metrics(response, metrics)  # should return True due to no match


def test_validate_bot_metrics_partial():
    """Test that validator handles responses with only one metric."""
    metrics = {"IAS": 0.5, "GAS": 0.3}
    response = "System status: IAS=0.500"  # only IAS mentioned
    assert validate_bot_metrics(
        response, metrics
    )  # should return True due to no full match
