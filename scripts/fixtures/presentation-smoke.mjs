// Synthetic editable deck for the actual-client supplied-runtime qualification.
import fs from 'node:fs/promises';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { Presentation, PresentationFile, FileBlob } from '@oai/artifact-tool';

const [workspaceDir, SKILL_DIR] = process.argv.slice(2);
const { finalizePresentation, resolvePresentationFont } = await import(pathToFileURL(
  path.join(SKILL_DIR, 'container_tools/artifact_tool_utils.mjs')));
const font = resolvePresentationFont();
const presentation = Presentation.create({ slideSize: { width: 1280, height: 720 } });
const slide = presentation.slides.add();
slide.background.fill = '#FFF7ED';
for (const [text, top, size] of [['Good morning', 160, 72], ['You bring care to the work you do.', 310, 36]]) {
  const shape = slide.shapes.add({ geometry: 'textbox',
    position: { left: 100, top, width: 1080, height: 120 },
    fill: 'none', line: { fill: 'none', width: 0 } });
  shape.text = text;
  shape.text.style = { typeface: font, fontSize: size, color: '#14261F' };
}
const build = path.join(workspaceDir, 'build');
const output = path.join(workspaceDir, 'output');
const candidatePath = path.join(build, 'candidate.pptx');
const finalPath = path.join(output, 'deck.pptx');
await fs.mkdir(output, { recursive: true });
await (await PresentationFile.exportPptx(presentation)).save(candidatePath);
await finalizePresentation({ workspaceDir, candidatePath, finalPath,
  explicitTotalSlideCount: 1,
  pythonExecutable: process.env.RUNTIME_PYTHON,
  integrityValidatorPath: path.join(SKILL_DIR, 'container_tools/inspect_presentation_package_integrity.py'),
  layoutValidatorPath: path.join(SKILL_DIR, 'container_tools/inspect_presentation_layout_geometry.py'),
  layoutArgs: ['--expected-slide-size-emu', '12192000,6858000', '--validate-heading-fit'],
  fontPolicy: { basis: 'design', families: [font] },
  verifyArtifactToolImport: true, receiptPath: path.join(build, 'finalization.json') });
const finalized = await PresentationFile.importPptx(await FileBlob.load(finalPath));
await fs.writeFile(path.join(output, 'slide.png'), Buffer.from(await
  (await finalized.export({ slide: finalized.slides.items[0], format: 'png', scale: 1 })).arrayBuffer()));
console.log(JSON.stringify({ status: 'completed', font, outputs: ['deck.pptx', 'slide.png'] }));
