# Development Notes — cthrobt

## Session: 2026-06-01 (Windows 11 environment setup)

### What was done
- Ported from macOS development environment to Windows 11
- Installed `pygame-ce 2.5.7` (pygame Community Edition — Python 3.14 has no official pygame wheel yet)
- Added `--mock` mode to `controller.py` for testing without a real gamepad
- Created `compare.py` for automated sent/received comparison
- Confirmed 100% pass rate in Renode simulation test

### Key decisions

**pygame-ce instead of pygame**
- Python 3.14 has no pre-built wheel for `pygame`
- `pygame-ce` (Community Edition) is API-compatible (`import pygame` works unchanged)
- Install: `pip install pygame-ce`

**Corporate proxy setup**
- Proxy: `http://tkyproxy-std.intra.tis.co.jp:8080` (auto-detected via PAC at `http://lbo-tky.intra.tis.co.jp/breakoutpac/tkyproxy-std.pac`)
- pip doesn't support PAC files — must use explicit proxy address
- pip.ini location: `C:\Users\<user>\AppData\Roaming\pip\pip.ini`
- Trusted hosts required for SSL bypass: `pypi.org pypi.python.org files.pythonhosted.org`

### Current state
- `controller.py` — real gamepad mode + `--mock` mode both working
- `simulator.py` — standalone debug server (use instead of bridge.py when no Renode)
- `compare.py` — generates Markdown report from sent vs received logs
- All scripts in `scripts/` for both Windows (.bat) and macOS (.sh)

## Next steps
- [ ] Test with real Nintendo Switch Pro Controller connected
- [ ] Adjust button/axis mapping if controller index differs from default SDL2 mapping
- [ ] Consider adding `--mock-seed` for reproducible random sequences
- [ ] Consider adding `--repeat` option to loop mock mode continuously

## Known issues / gotchas
- **Timing**: Renode processes UART bytes slower than real-time. `bridge.py` now waits for output to go silent (5s) before signaling "ready for compare"
- **Port conflict**: `simulator.py` and `bridge.py` both listen on port 7777 — never run both at the same time
- **Protocol**: Default is JSON. Binary mode exists but STM32 side only implements JSON parsing currently
