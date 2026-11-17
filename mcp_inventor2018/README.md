# MCP Inventor 2018 — V1 foundation

This is a local Windows MCP server. It must run on the same Windows computer as
Autodesk Inventor 2018 because the geometry bridge uses Inventor COM Automation.

## Current tools

- `inspect_pdf(path)`: extract selectable PDF text and page metadata.
- `render_pdf_page(path, page_number, dpi)`: return a page image for a vision-capable MCP host.
- `inventor_status()`: connect to the running Inventor instance.
- `inventor_list_parameters()`: inspect parameters in the active IPT.
- `inventor_create_extruded_rectangle(...)`: create a new rectangular IPT as a COM smoke test.

## Important scope

This is the first integration foundation, not yet a finished automatic drawing
reconstruction engine. The rectangle extrusion is a controlled COM test.
Arbitrary drawing interpretation, feature planning, holes/threads, sheet-metal,
assemblies, drawing generation and geometry verification are subsequent modules.
The model must not invent missing dimensions or infer exact dimensions from
page scale.

## Windows build

Build as a console executable because MCP stdio uses stdin/stdout. Do not use
PyInstaller `--windowed`.

```powershell
py -m pip install -r requirements.txt pyinstaller
pyinstaller --clean --onefile --console --name Inventor2018MCP server.py
```

The user workstation can run the packaged executable without installing Python.
Inventor 2018 must be installed and running. Configure the MCP host to launch
the executable as a stdio server.

## Safety

- Never overwrite an existing IPT.
- Never silently start another Inventor session.
- Keep source PDF unchanged.
- Require explicit model-side validation before a generated part is used for manufacture.
