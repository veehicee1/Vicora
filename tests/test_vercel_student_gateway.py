from pathlib import Path


def test_vercel_gateway_is_not_an_open_proxy_and_only_exposes_explicit_routes():
    source = Path("api/[...path].js").read_text(encoding="utf-8")
    for route in (
        "/api/public/info", "/api/public/school-logo",
        "/api/public/schools/resolve", "/api/public/school-applications",
        "/api/public/school-activation"
    ):
        assert route in source
    assert 'const ALLOWED_PREFIXES = ["/api/student/", "/api/platform/", "/api/android-host/", "/api/central/"]' in source
    assert 'process.env.VICORA_ENABLE_ADMIN_GATEWAY === "1"' in source
    assert 'path.startsWith("/api/admin/")' in source
    assert "x-vicora-platform-token" in source
    assert "x-vicora-host-token" in source
    assert '"authorization"' in source
    assert '"cookie"' in source
    assert "VICORA_API_ORIGIN" in source
    assert "ANDROID_HOST_ORIGIN" in source
    assert "Boolean(accessId) !== Boolean(accessSecret)" in source
    assert "CF-Access-Client-Id" in source
    assert "CF-Access-Client-Secret" in source
    assert 'origin.protocol !== "https:"' in source
    assert 'redirect: "manual"' in source
    assert "%2e|%2f|%5c" in source
    assert "String.fromCharCode(92)" in source


def test_vercel_serves_student_and_school_admin_portals():
    config = Path("vercel.json").read_text(encoding="utf-8")
    assert '"outputDirectory": "public"' in config
    assert '"framework": null' in config
    assert Path("public/home/index.html").is_file()
    assert Path("public/home/sw.js").is_file()
    assert Path("public/home/manifest.webmanifest").is_file()
    assert Path("public/register-school.html").is_file()
    assert Path("public/activate-school.html").is_file()
    assert Path("public/platform-admin.html").is_file()
    assert Path("public/admin/index.html").is_file()
    html = Path("public/home/index.html").read_text(encoding="utf-8")
    assert "/api/student" in html
    assert "/home/icon.svg" in html
    assert "/gtmc-logo.jpg" not in html
    admin = Path("public/admin/index.html").read_text(encoding="utf-8")
    assert "/api/admin" in admin
    maintained = Path("web/admin.html").read_text(encoding="utf-8")
    assert admin == maintained, "Keep the deployed Vercel Admin page synchronized with web/admin.html."
