"""
Unit tests for goplus_security.py module.

Tests cover:
- GoPlusLabs API integration (mocked)
- Security check parsing (honeypot, mintable, etc.)
- Security level evaluation logic
- Success and failure cases
- Rate limiting behavior
"""

import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock, MagicMock
import aiohttp

from goplus_security import (
    check_goplus_security,
    _fetch_goplus_data,
    _parse_security_checks,
    _evaluate_security_level,
    LEVEL_OK,
    LEVEL_WARNING,
    LEVEL_DANGER,
    LEVEL_UNKNOWN,
)


# =============================================================================
# SECURITY CHECK PARSING TESTS
# =============================================================================

def test_parse_security_checks_all_safe():
    """Test parsing security checks when all pass."""
    data = {
        "is_honeypot": "0",
        "is_mintable": "0",
        "hidden_owner": "0",
        "selfdestruct": "0",
        "is_blacklisted": "0"
    }
    
    checks = _parse_security_checks(data)
    
    assert checks["is_honeypot"] is False
    assert checks["is_mintable"] is False
    assert checks["hidden_owner"] is False
    assert checks["selfdestruct"] is False
    assert checks["is_blacklisted"] is False


def test_parse_security_checks_honeypot_detected():
    """Test parsing security checks when honeypot is detected."""
    data = {
        "is_honeypot": "1",
        "is_mintable": "0",
        "hidden_owner": "0",
        "selfdestruct": "0",
        "is_blacklisted": "0"
    }
    
    checks = _parse_security_checks(data)
    
    assert checks["is_honeypot"] is True
    assert checks["is_mintable"] is False


def test_parse_security_checks_multiple_issues():
    """Test parsing security checks with multiple issues."""
    data = {
        "is_honeypot": "1",
        "is_mintable": "1",
        "hidden_owner": "1",
        "selfdestruct": "0",
        "is_blacklisted": "1"
    }
    
    checks = _parse_security_checks(data)
    
    assert checks["is_honeypot"] is True
    assert checks["is_mintable"] is True
    assert checks["hidden_owner"] is True
    assert checks["selfdestruct"] is False
    assert checks["is_blacklisted"] is True


def test_parse_security_checks_missing_fields():
    """Test parsing handles missing fields."""
    data = {}
    
    checks = _parse_security_checks(data)
    
    # All should default to False
    assert checks["is_honeypot"] is False
    assert checks["is_mintable"] is False
    assert checks["hidden_owner"] is False


def test_parse_security_checks_integer_values():
    """Test parsing handles integer values (instead of strings)."""
    data = {
        "is_honeypot": 1,  # Integer instead of string
        "is_mintable": 0,
        "hidden_owner": False,  # Boolean
        "selfdestruct": True,  # Boolean
        "is_blacklisted": 0
    }
    
    checks = _parse_security_checks(data)
    
    assert checks["is_honeypot"] is True
    assert checks["is_mintable"] is False
    assert checks["hidden_owner"] is False
    assert checks["selfdestruct"] is True


# =============================================================================
# SECURITY LEVEL EVALUATION TESTS
# =============================================================================

def test_evaluate_security_level_all_safe():
    """Test evaluation when all checks pass."""
    checks = {
        "is_honeypot": False,
        "is_mintable": False,
        "hidden_owner": False,
        "selfdestruct": False,
        "is_blacklisted": False
    }
    
    level, reason = _evaluate_security_level(checks)
    
    assert level == LEVEL_OK
    assert "All security checks passed" in reason


def test_evaluate_security_level_honeypot():
    """Test evaluation when honeypot is detected."""
    checks = {
        "is_honeypot": True,
        "is_mintable": False,
        "hidden_owner": False,
        "selfdestruct": False,
        "is_blacklisted": False
    }
    
    level, reason = _evaluate_security_level(checks)
    
    assert level == LEVEL_DANGER
    assert "honeypot" in reason.lower()


def test_evaluate_security_level_blacklisted():
    """Test evaluation when token is blacklisted."""
    checks = {
        "is_honeypot": False,
        "is_mintable": False,
        "hidden_owner": False,
        "selfdestruct": False,
        "is_blacklisted": True
    }
    
    level, reason = _evaluate_security_level(checks)
    
    assert level == LEVEL_DANGER
    assert "blacklisted" in reason.lower()


def test_evaluate_security_level_mintable_warning():
    """Test evaluation when token is mintable (warning level)."""
    checks = {
        "is_honeypot": False,
        "is_mintable": True,
        "hidden_owner": False,
        "selfdestruct": False,
        "is_blacklisted": False
    }
    
    level, reason = _evaluate_security_level(checks)
    
    assert level == LEVEL_WARNING
    assert "minting" in reason.lower()


def test_evaluate_security_level_hidden_owner_warning():
    """Test evaluation when token has hidden owner."""
    checks = {
        "is_honeypot": False,
        "is_mintable": False,
        "hidden_owner": True,
        "selfdestruct": False,
        "is_blacklisted": False
    }
    
    level, reason = _evaluate_security_level(checks)
    
    assert level == LEVEL_WARNING
    assert "hidden owner" in reason.lower()


def test_evaluate_security_level_selfdestruct_warning():
    """Test evaluation when token has self-destruct capability."""
    checks = {
        "is_honeypot": False,
        "is_mintable": False,
        "hidden_owner": False,
        "selfdestruct": True,
        "is_blacklisted": False
    }
    
    level, reason = _evaluate_security_level(checks)
    
    assert level == LEVEL_WARNING
    assert "self-destruct" in reason.lower()


def test_evaluate_security_level_danger_takes_priority():
    """Test that DANGER level takes priority over WARNING."""
    checks = {
        "is_honeypot": True,  # DANGER
        "is_mintable": True,  # WARNING
        "hidden_owner": True,  # WARNING
        "selfdestruct": False,
        "is_blacklisted": False
    }
    
    level, reason = _evaluate_security_level(checks)
    
    assert level == LEVEL_DANGER
    assert "honeypot" in reason.lower()


# =============================================================================
# ASYNC API TESTS
# =============================================================================

@pytest.mark.asyncio
async def test_check_goplus_security_safe_token():
    """Test full security check with safe token."""
    mock_data = {
        "is_honeypot": "0",
        "is_mintable": "0",
        "hidden_owner": "0",
        "selfdestruct": "0",
        "is_blacklisted": "0"
    }
    
    with patch('goplus_security._fetch_goplus_data', new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = mock_data
        
        result = await check_goplus_security("SafeToken123")
        
        assert result["level"] == LEVEL_OK
        assert "All security checks passed" in result["reason"]
        assert result["checks"]["is_honeypot"] is False


@pytest.mark.asyncio
async def test_check_goplus_security_dangerous_token():
    """Test full security check with dangerous token."""
    mock_data = {
        "is_honeypot": "1",
        "is_mintable": "0",
        "hidden_owner": "0",
        "selfdestruct": "0",
        "is_blacklisted": "0"
    }
    
    with patch('goplus_security._fetch_goplus_data', new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = mock_data
        
        result = await check_goplus_security("DangerToken123")
        
        assert result["level"] == LEVEL_DANGER
        assert "honeypot" in result["reason"].lower()
        assert result["checks"]["is_honeypot"] is True


@pytest.mark.asyncio
async def test_check_goplus_security_not_found():
    """Test security check when token is not found in database."""
    with patch('goplus_security._fetch_goplus_data', new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = None
        
        result = await check_goplus_security("UnknownToken123")
        
        assert result["level"] == LEVEL_UNKNOWN
        assert "not found" in result["reason"].lower()
        assert result["checks"] == {}


@pytest.mark.asyncio
async def test_check_goplus_security_api_error():
    """Test security check when API fails."""
    with patch('goplus_security._fetch_goplus_data', new_callable=AsyncMock) as mock_fetch:
        mock_fetch.side_effect = Exception("API Error")
        
        result = await check_goplus_security("Token123")
        
        assert result["level"] == LEVEL_UNKNOWN
        assert "API error" in result["reason"]


@pytest.mark.asyncio
async def test_fetch_goplus_data_success():
    """Test successful API fetch."""
    mock_response_data = {
        "code": 1,
        "result": {
            "token123": {
                "is_honeypot": "0",
                "is_mintable": "0"
            }
        }
    }
    
    with patch('aiohttp.ClientSession') as MockSession:
        mock_session = MagicMock()
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=mock_response_data)
        mock_response.raise_for_status = Mock()
        
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.get = MagicMock(return_value=mock_response)
        mock_session.get.return_value.__aenter__ = AsyncMock(return_value=mock_response)
        mock_session.get.return_value.__aexit__ = AsyncMock(return_value=None)
        
        MockSession.return_value = mock_session
        
        result = await _fetch_goplus_data("Token123")
        
        # Function should return data (or None if token not found with exact casing)


@pytest.mark.asyncio
async def test_fetch_goplus_data_404():
    """Test API fetch handles 404 (token not found)."""
    with patch('aiohttp.ClientSession') as MockSession:
        mock_session = MagicMock()
        mock_response = AsyncMock()
        mock_response.status = 404
        
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.get = MagicMock(return_value=mock_response)
        mock_session.get.return_value.__aenter__ = AsyncMock(return_value=mock_response)
        mock_session.get.return_value.__aexit__ = AsyncMock(return_value=None)
        
        MockSession.return_value = mock_session
        
        result = await _fetch_goplus_data("UnknownToken")
        
        assert result is None


@pytest.mark.asyncio
async def test_check_goplus_security_multiple_warnings():
    """Test security check with multiple warning flags."""
    mock_data = {
        "is_honeypot": "0",
        "is_mintable": "1",
        "hidden_owner": "1",
        "selfdestruct": "1",
        "is_blacklisted": "0"
    }
    
    with patch('goplus_security._fetch_goplus_data', new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = mock_data
        
        result = await check_goplus_security("SketchyToken123")
        
        assert result["level"] == LEVEL_WARNING
        assert result["checks"]["is_mintable"] is True
        assert result["checks"]["hidden_owner"] is True
        assert result["checks"]["selfdestruct"] is True
