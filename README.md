# PDF2Inventor Local Edition V0.9

Offline-first desktop application for reading vector PDF mechanical drawings and creating editable native Autodesk Inventor 2018 features through the Inventor COM API.

## Design principles

- No OpenAI API key, paid AI endpoint, cloud upload or GPU is required for local PDF analysis.
- PDF files are analyzed locally with PyMuPDF.
- PDF coordinates remain PDF points (1/72 inch). They are never silently treated as millimetres.
- Drawing dimensions, scale calibration, extrusion depth and feature intent must be explicit. The software must not invent missing geometry.
- Every model-changing operation asks for user confirmation and saves a backup before editing the IPT/IAM.

## Native Inventor 2018 features

### Part features

- Rectangle/Circle Sketch + Extrude/Cut.
- Custom closed profile extrude: polyline, circle and line/arc segment loops on XY, XZ or YZ origin planes; optional parallel offset plane.
- Revolve: closed section profile around an explicit sketch axis, full 360 degrees or a specified partial angle. This is suitable for turned components such as shafts, bushes and pulleys when the section and axis are known.
- Control-point spline profile extrude: closed 2D spline boundary with explicit control points.
- Sweep: existing named profile Sketch swept along a selected line, arc or spline in an existing named path Sketch.
- Loft: two or more existing section Sketches in explicitly supplied order.
- Hole: native drilled feature from explicit sketch point centres; through-all or blind depth.
- Standard Thread: native thread on a selected cylindrical face with explicit thread-table designation and start edge.
- Fillet and Chamfer: native edge finishing features using current 1-based edge indices.
- Circular and one-/two-direction rectangular feature patterns.
- Shell: explicit thickness and optional faces to remove.
- Mirror: named existing features mirrored about an explicit work plane.

### IAM assembly

- Create a new IAM by inserting existing IPT documents at explicit XYZ translations in millimetres.
- Add native Mate and Flush constraints using explicitly identified planar faces/work planes.
- Add native Insert constraints using explicitly identified circular edges.
- Analyze interference between all or selected component occurrences and report the interfering pair and overlap volume.
- Constraint entities must be read from the current assembly/model topology. Indexes may change after model edits. Insert is restricted to circular edges. Automatic rotational alignment, axis inference, joint authoring and automatic constraint solving from drawing intent are not claimed.

## PDF vector to Feature planner

The PDF tab includes **Tạo Feature từ vector kín**.

1. Open the source vector PDF and analyze it locally.
2. Select one or more recognized closed line/rectangle paths from the current page.
3. Select whether the first selected boundary is calibrated by its horizontal or vertical extent, then enter the matching dimension printed on the drawing. The app calculates mm per PDF point from that explicit measurement.
4. Enter the actual Extrude depth in millimetres.
5. Select the target IPT component and sketch plane.
6. The application creates the Feature command package, validates it, and opens the CAD command review tab for confirmation.

The planner deliberately supports a conservative subset only:
- Closed vector outlines made from straight line segments or PDF rectangle primitives.
- The user selects path indices; the software does not decide which outline is the intended part profile.
- The scale factor and depth are explicit user inputs. Textual dimension candidates extracted from the page are not yet automatically associated with dimension lines or applied to the generated geometry.
- It does not yet interpret hidden lines, section views, multi-view correspondence, dimension arrows, arcs/circles/splines, thread callouts or assembly positions into a complete manufacturing model.
- Raster/scan-only pages are not converted into geometry by this planner.

The PDF planner is therefore an assisted vector-to-Feature workflow, not a fully autonomous drawing-to-3D reconstruction engine. It is designed to avoid silently scaling or dimensioning a model incorrectly.

## Command packages and safety

- Native CAD commands are validated before execution.
- Part Feature chains can contain multiple commands in order when they target the same component and IPT.
- Each step creates its own backup and commits/saves separately. If a later step fails, earlier completed steps remain applied; restore the corresponding backup files to roll back.
- Assembly constraints and interference analysis are standalone commands and target a saved IAM component.
- Face, edge, path, feature and work-plane indices are 1-based and must refer to the current model revision.
- Loft profiles must exist as closed section Sketches in the IPT. Sweep profile and path Sketches must exist and the selected path curve must be valid and connected.
- Revolve profile geometry must be a valid closed section that does not create self-intersection or invalid geometry around the specified axis.
- Spline profile creation currently supports closed control-point splines. Arbitrary open freeform surfaces and spline-based 3D reconstruction from orthographic drawings are not implemented.

## Build Windows x64 EXE

GitHub Actions builds the standalone EXE for branch \`feature/v0.9-complete\`.

- Workflow: \`.github/workflows/build-windows-exe.yml\`
- Artifact name: \`PDF2Inventor_AI_V0_9_Windows_x64\`
- Executable in the artifact: \`PDF2Inventor_AI_V0_9.exe\`
- Runtime target: Windows x64, Autodesk Inventor 2018 installed locally for COM operations.

The GitHub Actions job checks Python compilation/imports, runs offline unit tests and packages the application. The build pipeline cannot launch Autodesk Inventor 2018 or verify actual COM geometry operations. Real Inventor feature execution must be validated on a Windows machine with Inventor 2018.
