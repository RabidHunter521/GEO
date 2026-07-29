from app.services.toolkit_dimension_service import derive_toolkit_dimensions


def test_robots_access_drives_technical_foundations():
    state = derive_toolkit_dimensions({
        "robots_verified": True,
        "schema_verified": False,
        "llms_verified": False,
        "llms_full_verified": False,
    })
    assert state.technical_foundations_verified is True
    assert state.structured_data_verified is False


def test_llms_files_do_not_drive_score_dimensions():
    state = derive_toolkit_dimensions({
        "robots_verified": False,
        "schema_verified": False,
        "llms_verified": True,
        "llms_full_verified": True,
    })
    assert state.technical_foundations_verified is False
    assert state.structured_data_verified is False


def test_schema_drives_structured_data_only():
    state = derive_toolkit_dimensions({
        "robots_verified": False,
        "schema_verified": True,
        "llms_verified": False,
        "llms_full_verified": False,
    })
    assert state.technical_foundations_verified is False
    assert state.structured_data_verified is True
