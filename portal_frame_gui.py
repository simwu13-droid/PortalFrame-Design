"""
SpaceGass 2D Portal Frame Generator — GUI — Backward-compatible wrapper.

The actual implementation lives in portal_frame/gui/.
"""

from portal_frame.gui.app import PortalFrameApp

if __name__ == "__main__":
    app = PortalFrameApp()
    app.mainloop()
