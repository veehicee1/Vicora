from pathlib import Path


def test_platform_admin_bridge_keeps_apps_script_key_server_side():
    source = Path("api/central/admin.js").read_text(encoding="utf-8")
    assert '"admin.listApplications"' in source
    assert '"admin.decideApplication"' in source
    assert '"admin.listSchools"' in source
    assert '"admin.setSchoolStatus"' in source
    assert "VICORA_CENTRAL_APPS_SCRIPT_URL" in source
    assert "VICORA_PLATFORM_ADMIN_KEY" in source
    assert "VICORA_PLATFORM_ADMIN_TOKEN" in source
    assert "timingSafeEqual" in source
    assert "X-VICORA-PLATFORM-TOKEN" in source
    assert "adminKey" in source
    assert "redirect: \"follow\"" in source
    assert "script.google.com" in source
    assert "module.exports.config = { api: { bodyParser: false } }" in source


def test_platform_admin_page_uses_protected_bridge_and_never_persists_token():
    page = Path("public/platform-admin.html").read_text(encoding="utf-8")
    assert 'fetch("/api/central/admin"' in page
    assert "X-VICORA-PLATFORM-TOKEN" in page
    assert "admin.listApplications" in page
    assert "admin.decideApplication" in page
    assert "admin.listSchools" in page
    assert "admin.setSchoolStatus" in page
    assert "Suspend school" in page
    assert "Reactivate school" in page
    assert "Registered schools" in page
    assert "localStorage" not in page
    assert "sessionStorage" not in page
    assert "VICORA_PLATFORM_ADMIN_KEY" not in page


def test_school_status_control_is_scoped_to_existing_schools_and_revokes_sessions():
    source = Path("apps-script/Code.gs").read_text(encoding="utf-8")
    assert "case 'admin.setSchoolStatus': requirePlatformAdmin_(body); result = setSchoolStatus_(body); break;" in source
    assert "function setSchoolStatus_(b)" in source
    assert "['approved','suspended']" in source
    assert "school.status === status" in source
    assert "school_id === schoolId" in source
    assert "revoked: 'true'" in source
    assert "school.suspended" in source
    assert "school.reactivated" in source
