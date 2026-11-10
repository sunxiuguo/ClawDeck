"""Non-Steam games (Steam shortcuts), #161."""
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "py_modules"))

from clawdeck import optiscaler, shortcuts, xess  # noqa: E402


def _kv(d: dict) -> bytes:
    out = b""
    for k, v in d.items():
        if isinstance(v, dict):
            out += b"\x00" + k.encode() + b"\x00" + _kv(v)
        elif isinstance(v, int):
            out += b"\x02" + k.encode() + b"\x00" + struct.pack("<i", v)
        else:
            out += b"\x01" + k.encode() + b"\x00" + v.encode() + b"\x00"
    return out + b"\x08"


def _touch(p, data=b"x"):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "wb") as f:
        f.write(data)
    return p


def _setup(tmp_path):
    home = tmp_path / "home"
    games = tmp_path / "games"
    sb = _touch(str(games / "Stellar Blade/SB/Binaries/Win64/SB-Win64-Shipping.exe"))
    os.makedirs(games / "Stellar Blade/Engine/Plugins", exist_ok=True)
    sifu = _touch(str(games / "Sifu/Sifu.exe"))
    icon = _touch(str(games / "Sifu/icon.png"), b"\x89PNG....")
    vdf = {"shortcuts": {
        "0": {"appid": -1234567890, "AppName": "Stellar Blade", "Exe": f'"{sb}"', "StartDir": f'"{os.path.dirname(sb)}"',
              "LaunchOptions": 'STEAM_COMPAT_DATA_PATH="/data/pfx/sb" %command%', "icon": ""},
        "1": {"appid": 287654321, "appname": "Sifu", "exe": f'"{sifu}"', "LaunchOptions": "", "icon": icon},
        "2": {"appid": 111, "AppName": "Moonlight", "Exe": '"/usr/bin/moonlight"', "LaunchOptions": ""},
    }}
    _touch(str(home / shortcuts.USERDATA / "12345/config/shortcuts.vdf"), b"\x00shortcuts\x00" + _kv(vdf["shortcuts"]) + b"\x08")
    return home, games


def test_shortcuts_keep_windows_games_with_their_top_folder_and_prefix(tmp_path):
    home, games = _setup(tmp_path)
    sc = {s["name"]: s for s in shortcuts.shortcuts(str(home))}
    assert set(sc) == {"Stellar Blade", "Sifu"}                       # Moonlight (not an .exe) left out
    sb = sc["Stellar Blade"]
    assert sb["appid"] == str(-1234567890 & 0xFFFFFFFF)               # Steam's unsigned 32-bit shortcut id
    assert sb["dir"] == str(games / "Stellar Blade")                   # out of Binaries/Win64 and the project folder
    assert sb["compat"] == "/data/pfx/sb"                              # its own prefix from the launch options
    assert sc["Sifu"]["compat"].endswith("compatdata/287654321") and sc["Sifu"]["dir"] == str(games / "Sifu")
    assert xess.prefix_dir(str(home), sb["appid"]) == "/data/pfx/sb/pfx/drive_c"
    assert xess.steam_install_dir(str(home), "287654321") == str(games / "Sifu")
    assert xess.steam_app_name(str(home), "287654321") == "Sifu"
    names = [g["name"] for g in xess.installed_games(str(home))]
    assert names == ["Sifu", "Stellar Blade"]
    assert shortcuts.icon_url(str(home), "287654321").startswith("data:image/png;base64,")
    assert shortcuts.icon_url(str(home), sb["appid"]) is None


def test_a_broken_shortcuts_file_is_skipped(tmp_path):
    home = tmp_path / "home"
    _touch(str(home / shortcuts.USERDATA / "1/config/shortcuts.vdf"), b"\x00shortcuts\x00\x05bad")
    assert shortcuts.shortcuts(str(home)) == []


def test_compat_path_forms():
    assert shortcuts.compat_path("STEAM_COMPAT_DATA_PATH=/a/b %command%") == "/a/b"
    assert shortcuts.compat_path("FOO=1 STEAM_COMPAT_DATA_PATH='/a b' %command%") == "/a b"
    assert shortcuts.compat_path("%command%") is None


def test_unreal_launcher_stub_is_not_where_optiscaler_goes(tmp_path):
    """#162 Gothic 1 Remake: a 310 KB G1R-Win64-Shipping.exe stub in the top folder, the 175 MB game in G1R/Binaries/Win64."""
    _touch(str(tmp_path / "G1R-Win64-Shipping.exe"), b"x" * 300)
    _touch(str(tmp_path / "G1R/Binaries/Win64/G1R-Win64-Shipping.exe"), b"x" * 5000)
    assert optiscaler.main_exe_dir(str(tmp_path)) == str(tmp_path / "G1R/Binaries/Win64")


def _shortcut_prefix(tmp_path, launch_options):
    home = tmp_path / "home"
    exe = _touch(str(tmp_path / "games/Game.exe"))
    entry = {"appid": 123, "AppName": "Game", "Exe": exe, "LaunchOptions": launch_options}
    _touch(str(home / shortcuts.USERDATA / "1/config/shortcuts.vdf"), _kv({"shortcuts": {"0": entry}}))
    return home, home / xess.COMPATDATA / "123"


def test_explicit_prefix_wins_over_empty_and_populated_steam_directories(tmp_path):
    custom = tmp_path / "custom prefix"
    home, default = _shortcut_prefix(tmp_path, f'STEAM_COMPAT_DATA_PATH="{custom}" %command%')
    default.mkdir(parents=True)
    expected = str(custom / "pfx/drive_c")
    assert xess.prefix_dir(str(home), "123") == expected
    (default / "pfx/drive_c").mkdir(parents=True)
    assert xess.prefix_dir(str(home), "123") == expected
    # A selected prefix need not exist yet; never silently read/write the other prefix.
    assert not custom.exists()


def test_default_prefix_without_explicit_path(tmp_path):
    home, default = _shortcut_prefix(tmp_path, "STEAM_COMPAT_DATA_PATH= %command%")
    assert xess.prefix_dir(str(home), "123") == str(default / "pfx/drive_c")
    default.mkdir(parents=True)
    assert xess.prefix_dir(str(home), "123") == str(default / "pfx/drive_c")
    assert xess.prefix_dir(str(home), "456") == str(home / xess.COMPATDATA / "456/pfx/drive_c")


def test_relative_prefix_keeps_existing_parser_semantics(tmp_path):
    home, default = _shortcut_prefix(tmp_path, "STEAM_COMPAT_DATA_PATH=relative/prefix %command%")
    default.mkdir(parents=True)
    assert xess.prefix_dir(str(home), "123") == "relative/prefix/pfx/drive_c"


def test_custom_prefix_proof_and_shim_ignore_steam_directory(tmp_path, monkeypatch):
    from clawdeck import userexec, xmxscope

    custom = tmp_path / "custom"
    home, default = _shortcut_prefix(tmp_path, f"STEAM_COMPAT_DATA_PATH='{custom}' %command%")
    default.mkdir(parents=True)
    drive = custom / "pfx/drive_c"
    _touch(str(drive / "igdext_kernels/anv_canary"))
    _touch(str(drive / "igdext_kernels/map.txt"), b"kernel-one\nkernel-two\n")
    proof = xess.xmx_proof(str(home), "123")
    assert proof["state"] == "ok"
    assert proof["kernels"] == 2
    sys32 = drive / "windows/system32"
    sys32.mkdir(parents=True)
    pkg = tmp_path / "package"
    _touch(str(pkg / "igdext64.dll"), b"synthetic-shim")
    _touch(str(pkg / "ControlLib.dll"), b"synthetic-control")
    monkeypatch.setattr(userexec, "chown_tree", lambda *_: None)
    result = xmxscope.prefix_shim(str(home), "123", str(pkg))
    assert result["ok"] and result["placed"]
    assert (sys32 / "driverstore/filerepository/igd_faux.inf_1/igdext64.dll").read_bytes() == b"synthetic-shim"
    assert (sys32 / "ControlLib.dll").read_bytes() == b"synthetic-control"
    assert not list(default.iterdir())
    assert not xmxscope.prefix_shim(str(home), "123", str(pkg))["placed"]
