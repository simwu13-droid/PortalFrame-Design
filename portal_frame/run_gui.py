"""GUI entry point for the portal frame generator."""


def main():
    from portal_frame.gui.app import PortalFrameApp
    app = PortalFrameApp()
    app.mainloop()


if __name__ == "__main__":
    main()
