# PDF2Inventor Local Edition V0.6 · Offline vector-first CAD automation

## Local PDF processing
- Opens PDF locally with PyMuPDF.
- Extracts selectable text, text span coordinates, dimension-like tokens, vector paths and page metrics.
- Exports a JSON report. No OpenAI API, no PDF upload, no GPU requirement.
- PDF point coordinates are not assumed to be millimetres. Drawing dimensions remain the authority for scale calibration.
- Automatic full drawing-to-solid reconstruction is not claimed: ambiguous views, hidden geometry, missing dimensions and scan-only pages require additional interpretation/OCR.

## Inventor 2018 native feature operations currently implemented
- Rectangle and circle Sketch + Extrude/Cut.
- create_profile_extrude: custom closed polyline/circle loops on XY, XZ or YZ origin planes, including offset_mm parallel planes, then Extrude/Join/New Body/Cut.
- create_hole: native drilled Hole feature with multiple sketch-point locations, through-all or blind depth.
- create_thread: native standard thread on an existing cylindrical face using Inventor thread-table designation.
- create_fillet: native constant-radius Fillet on explicit 1-based edge indices.
- create_chamfer: native distance Chamfer on explicit 1-based edge indices.
- create_circular_pattern: native circular feature pattern using named existing features and a work-axis index.
- create_rectangular_pattern: native one- or two-direction rectangular feature pattern using named existing features and work-axis indices.
- create_assembly_iam: creates a new IAM and inserts existing IPT files at explicitly supplied XYZ positions in millimetres.

## Advanced profile JSON example
    {
      "op": "create_profile_extrude", "component_id": "PART_001", "unit": "mm",
      "plane": "XY",
      "loops": [
        {"type": "polyline", "points": [[0,0],[120,0],[110,60],[0,60]]},
        {"type": "circle", "center_x": 30, "center_y": 30, "radius": 5}
      ],
      "distance": 8, "operation": "new_body", "direction": "positive"
    }

## Fillet / Chamfer
- Fillet: op=create_fillet, edge_indices=[1,2], radius=2, unit=mm.
- Chamfer: op=create_chamfer, edge_indices=[3], distance=1, unit=mm.

## Pattern
- Circular: op=create_circular_pattern, feature_names=["Hole1"], axis_index=3, count=6, angle_deg=360, unit=mm.
- Rectangular (one direction): op=create_rectangular_pattern, feature_names=["Rib1"], axis_index=1, count=4, spacing_mm=25, unit=mm.

## IAM assembly
- op=create_assembly_iam, output_path='C:/CAD/Assembly.iam'.
- components is a list of {ipt_path, position_mm:[x,y,z], occurrence_name?}.
- This currently places IPTs by translation; it does not create automatic mates, joints, rotational alignment or interference solving.

## Safety and limitations
- Each geometry, edge finishing, pattern or assembly command must be submitted in its own JSON package.
- Fillet/chamfer edge indices are 1-based indices in the current body's Edges collection. They can change after topology changes; re-inspect the model before reusing them.
- Pattern features must exist by exact feature name; work-axis indices must match the active IPT.
- Thread face/edge indices and fillet/chamfer edge indices must be read from the current model topology. These indices can change after editing features.
- The Inventor tab includes a read-only B-rep face/edge inventory for identifying current face and edge indices.
- Custom profile creation currently supports straight polyline segments and circles; splines, arcs, loft, sweep, revolve, shell, sheet-metal folds, variable fillets and full automatic multi-feature reconstruction are not yet supported.
- Threading is native standard-thread feature creation on a selected cylindrical face; it does not yet auto-detect all thread callouts or choose faces without topology review.
- Every model edit makes a backup first and asks the user to confirm before applying.
- GitHub Actions validates Python and packages the EXE; it cannot certify Inventor COM geometry. Real Inventor 2018 validation remains necessary.

## Build
- GitHub Actions builds a Windows x64 one-file EXE on pushes to feature/v0.6-local-edition.
- Download artifact PDF2Inventor_AI_Windows_x64 from the Actions run after it completes.

## Ordered multi-feature plans
A command package may contain several geometry operations in sequence when all commands target the same component_id and IPT. Each feature creates its own backup. If any step fails, execution stops and reports completed steps and backups; earlier successful steps remain applied until restored from backup.
