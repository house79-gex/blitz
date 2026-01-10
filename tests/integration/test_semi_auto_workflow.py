"""Integration tests for semi-auto workflow."""

import pytest
from unittest.mock import Mock, patch, MagicMock


@pytest.mark.integration
def test_semi_auto_page_initialization(qapp, mock_machine):
    """Test semi-auto page initializes."""
    from qt6_app.ui_qt.pages.semi_auto_page import SemiAutoPage
    
    appwin = Mock()
    appwin.machine = mock_machine
    appwin.machine_adapter = Mock()
    
    # Mock the required attributes
    with patch('qt6_app.ui_qt.pages.semi_auto_page.get_metro_manager'):
        with patch('qt6_app.ui_qt.pages.semi_auto_page.ProfilesStore', None):
            page = SemiAutoPage(appwin)
            assert page is not None


@pytest.mark.integration
def test_semi_auto_mode_detection(qapp, mock_machine, sample_mode_config):
    """Test mode detection in semi-auto page."""
    from qt6_app.ui_qt.pages.semi_auto_page import SemiAutoPage
    
    appwin = Mock()
    appwin.machine = mock_machine
    appwin.machine_adapter = Mock()
    
    with patch('qt6_app.ui_qt.pages.semi_auto_page.get_metro_manager'):
        with patch('qt6_app.ui_qt.pages.semi_auto_page.ProfilesStore', None):
            with patch('qt6_app.ui_qt.pages.semi_auto_page.read_settings', return_value={}):
                page = SemiAutoPage(appwin)
                
                # Verify mode config is initialized
                assert hasattr(page, '_mode_config')
                assert hasattr(page, '_mode_detector')
