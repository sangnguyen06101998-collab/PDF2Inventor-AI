# Cad3Dify Windows EXE builder

This branch builds a Windows x64 packaged desktop launcher for the upstream MIT-licensed project https://github.com/neka-nat/cad3dify.

## Important before running

- Upstream Cad3Dify converts a 2D drawing image into a STEP model using an online LLM API. It is not a local/offline converter and does not include free AI inference.
- You must supply your own valid OpenAI, Anthropic or Google API key inside the app. API use may cost money.
- The bundled UI accepts PDF, PNG and JPG. PDF pages are rasterized locally before the selected AI provider receives the drawing image.
- The original upstream pipeline executes AI-generated Python/CadQuery code on the local computer. Do not use sensitive drawings unless you are authorized to send them to the provider; use a standard Windows account, not an administrator account.
- Generated STEP geometry and dimensions must be checked in a CAD system before manufacturing. This is an experimental AI workflow, not a tolerance-certified CAD translator.

## Build

The GitHub Actions workflow checks out the upstream repository at its current main branch, installs its declared dependencies, packages the Streamlit app with PyInstaller and uploads Cad3Dify_Windows_x64.zip.

The ZIP contains a Cad3Dify directory. Extract the entire directory and double-click Cad3Dify.exe. Keep the _internal and app folders next to the EXE.

The application starts a local web interface at 127.0.0.1 and opens it in the default browser. Use the sidebar "Thoát Cad3Dify" button to close the local server.

This is an onedir build: the ZIP is larger than a single EXE, but is more reliable for CadQuery/OpenCascade native libraries.
