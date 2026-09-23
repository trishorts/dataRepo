const pptxgen = require("pptxgenjs");
const React = require("react");
const ReactDOMServer = require("react-dom/server");
const sharp = require("sharp");
const fa = require("react-icons/fa");

const OUT = process.argv[2];

const C = {
  night: "1E1B4B", indigo: "4F46E5", teal: "0E7490", magenta: "A21CAF", amber: "D97706",
  green: "15803D", ink: "1C1B22", muted: "5B5968", tint: "EEF0FF", card: "F6F5FB",
  white: "FFFFFF", lav: "C7C9FF",
};
const HEAD = "Arial";
const BODY = "Calibri";

async function icon(Comp, color, size = 256) {
  const svg = ReactDOMServer.renderToStaticMarkup(
    React.createElement(Comp, { color: "#" + color, size: String(size) })
  );
  const png = await sharp(Buffer.from(svg)).png().toBuffer();
  return "image/png;base64," + png.toString("base64");
}

// An icon on a filled circle: the deck's one repeated motif.
async function badge(slide, Comp, x, y, d, fill, fg = C.white) {
  slide.addShape("ellipse", { x, y, w: d, h: d, fill: { color: fill }, line: { color: fill } });
  const pad = d * 0.24;
  slide.addImage({ data: await icon(Comp, fg), x: x + pad, y: y + pad, w: d - 2 * pad, h: d - 2 * pad });
}

function title(slide, text, color = C.ink) {
  slide.addText(text, {
    x: 0.6, y: 0.4, w: 12.1, h: 0.9, fontFace: HEAD, fontSize: 32, bold: true, color,
    margin: 0, isTextBox: true,
  });
}

(async () => {
  const pres = new pptxgen();
  pres.layout = "LAYOUT_WIDE"; // 13.33 x 7.5
  pres.title = "dataRepo: an AI-ready repository of reanalysed aging proteomics";

  // 1. Title ---------------------------------------------------------------------------------
  {
    const s = pres.addSlide();
    s.background = { color: C.night };
    await badge(s, fa.FaDatabase, 0.8, 1.35, 1.1, C.indigo);
    s.addText("dataRepo", {
      x: 0.8, y: 2.65, w: 11.5, h: 1.2, fontFace: HEAD, fontSize: 60, bold: true,
      color: C.white, margin: 0, isTextBox: true,
    });
    s.addText("An AI-ready repository of reanalysed aging proteomics", {
      x: 0.8, y: 3.85, w: 11.5, h: 0.7, fontFace: BODY, fontSize: 26, color: C.lav,
      margin: 0, isTextBox: true,
    });
    s.addText("NCEMS working group on aging  ·  Smith lab, University of Wisconsin–Madison  ·  September 2026", {
      x: 0.8, y: 6.3, w: 11.5, h: 0.5, fontFace: BODY, fontSize: 16, color: "A5A8E0",
      margin: 0, isTextBox: true,
    });
    s.addNotes(
      "dataRepo is the storage and serving half of the working group's reanalysis effort. " +
      "The aging pipeline produces the results; dataRepo makes them comparable, checkable and queryable."
    );
  }

  // 2. The problem ---------------------------------------------------------------------------
  {
    const s = pres.addSlide();
    s.background = { color: C.white };
    title(s, "Public proteomics: plentiful, but not comparable");
    const rows = [
      [fa.FaServer, C.teal, "Thousands of datasets are public in PRIDE",
        "Raw spectra are deposited, so anyone can reanalyse them."],
      [fa.FaRandom, C.magenta, "Every lab processed its own way",
        "Different search engines, protein databases, FDR rules and file formats. The published tables cannot be pooled."],
      [fa.FaDna, C.indigo, "Genomics met this problem first",
        "Uniform reprocessing of public RNA-seq (for example recount and ARCHS4) is what made thousands of experiments comparable."],
    ];
    let y = 1.6;
    for (const [ic, col, head, body] of rows) {
      await badge(s, ic, 0.6, y, 0.8, col);
      s.addText(head, { x: 1.65, y: y - 0.05, w: 6.2, h: 0.45, fontFace: HEAD, fontSize: 19, bold: true, color: C.ink, margin: 0, isTextBox: true });
      s.addText(body, { x: 1.65, y: y + 0.42, w: 6.2, h: 0.8, fontFace: BODY, fontSize: 15, color: C.muted, margin: 0, valign: "top", isTextBox: true });
      y += 1.6;
    }
    s.addShape("roundRect", { x: 8.4, y: 1.7, w: 4.3, h: 4.5, fill: { color: C.tint }, line: { color: C.tint }, rectRadius: 0.15 });
    s.addText([
      { text: "Our approach", options: { fontFace: HEAD, fontSize: 20, bold: true, color: C.indigo, breakLine: true } },
      { text: " ", options: { fontSize: 8, breakLine: true } },
      { text: "Take the raw spectra, not the authors' tables. Search every dataset with one pipeline, store every result in one format, and keep a record of how each number was made.", options: { fontFace: BODY, fontSize: 17, color: C.ink } },
    ], { x: 8.75, y: 2.0, w: 3.65, h: 3.9, valign: "top", margin: 0, isTextBox: true });
    s.addNotes("The analogy for genomicists: this is uniform reprocessing, applied to mass spectrometry.");
  }

  // 3. What it does: the flow ----------------------------------------------------------------
  {
    const s = pres.addSlide();
    s.background = { color: C.white };
    title(s, "From raw spectra to answers, in one path");
    const steps = [
      [fa.FaCloudDownloadAlt, C.teal, "PRIDE", "Public raw spectra from aging studies"],
      [fa.FaCogs, C.indigo, "aging-pipeline", "One search for all: MetaMorpheus with GPTMD to discover PTMs, FlashLFQ to quantify"],
      [fa.FaDatabase, C.magenta, "dataRepo", "One schema, versioned files, every count checked against the search engine's own"],
    ];
    const w = 3.0, gap = 0.55, x0 = 0.6, y = 2.0;
    steps.forEach(() => {});
    for (let i = 0; i < steps.length; i++) {
      const [ic, col, head, body] = steps[i];
      const x = x0 + i * (w + gap);
      s.addShape("roundRect", { x, y, w, h: 3.3, fill: { color: C.card }, line: { color: "E4E1EA" }, rectRadius: 0.12 });
      await badge(s, ic, x + (w - 0.9) / 2, y + 0.3, 0.9, col);
      s.addText(head, { x: x + 0.2, y: y + 1.35, w: w - 0.4, h: 0.45, fontFace: HEAD, fontSize: 19, bold: true, color: C.ink, align: "center", margin: 0, isTextBox: true });
      s.addText(body, { x: x + 0.25, y: y + 1.85, w: w - 0.5, h: 1.3, fontFace: BODY, fontSize: 14, color: C.muted, align: "center", valign: "top", margin: 0, isTextBox: true });
      s.addShape("rightArrow", { x: x + w + 0.08, y: y + 1.35, w: gap - 0.16, h: 0.45, fill: { color: "B9B7C9" }, line: { color: "B9B7C9" } });
    }
    // The three doors.
    const doors = [
      [fa.FaGlobe, C.teal, "Website", "for people"],
      [fa.FaRobot, C.indigo, "AI agents", "ask in plain language"],
      [fa.FaFileDownload, C.amber, "Bulk files", "for your own analysis"],
    ];
    const dx = x0 + 3 * (w + gap);
    for (let i = 0; i < doors.length; i++) {
      const [ic, col, head, body] = doors[i];
      const yy = 1.95 + i * 1.15;
      await badge(s, ic, dx, yy, 0.75, col);
      s.addText([
        { text: head, options: { fontFace: HEAD, fontSize: 17, bold: true, color: C.ink, breakLine: true } },
        { text: body, options: { fontFace: BODY, fontSize: 14, color: C.muted } },
      ], { x: dx + 0.9, y: yy, w: 1.9, h: 0.8, valign: "middle", margin: 0, isTextBox: true });
    }
    s.addText("dataRepo never re-runs a search. It stores, checks and serves what the pipeline produced.", {
      x: 0.6, y: 5.85, w: 12.1, h: 0.5, fontFace: BODY, fontSize: 16, italic: true, color: C.indigo, margin: 0, isTextBox: true,
    });
    s.addNotes("Two projects: aging searches, dataRepo stores and serves. Keeping them separate means a stored result can always be traced to the exact search that produced it.");
  }

  // 4. What it holds -------------------------------------------------------------------------
  {
    const s = pres.addSlide();
    s.background = { color: C.white };
    title(s, "What it holds, down to the residue");
    const cards = [
      [fa.FaWaveSquare, C.teal, "Spectrum matches", "Every identification, with a universal spectrum identifier that points back to the exact scan."],
      [fa.FaLink, C.indigo, "Peptidoforms", "Modified peptides written in the ProForma standard, so a modification is part of the sequence."],
      [fa.FaLayerGroup, C.magenta, "Protein groups", "Ambiguity is kept, not hidden: shared peptides stay shared."],
      [fa.FaMapMarkerAlt, C.amber, "PTM sites", "Residue and position on the protein, with the evidence behind each site."],
      [fa.FaChartBar, C.green, "Quantities", "Label-free intensities per run, with how each was calculated."],
      [fa.FaFlask, C.teal, "Sample metadata", "Organism, tissue and age as deposited in the SDRF, when the authors supplied them."],
    ];
    const cw = 3.85, ch = 1.95, gx = 0.3, gy = 0.3, x0 = 0.6, y0 = 1.5;
    for (let i = 0; i < cards.length; i++) {
      const [ic, col, head, body] = cards[i];
      const x = x0 + (i % 3) * (cw + gx), y = y0 + Math.floor(i / 3) * (ch + gy);
      s.addShape("roundRect", { x, y, w: cw, h: ch, fill: { color: C.card }, line: { color: "E4E1EA" }, rectRadius: 0.1 });
      await badge(s, ic, x + 0.25, y + 0.3, 0.65, col);
      s.addText(head, { x: x + 1.05, y: y + 0.3, w: cw - 1.25, h: 0.65, fontFace: HEAD, fontSize: 17, bold: true, color: C.ink, valign: "middle", margin: 0, isTextBox: true });
      s.addText(body, { x: x + 0.25, y: y + 1.05, w: cw - 0.5, h: 0.8, fontFace: BODY, fontSize: 13.5, color: C.muted, valign: "top", margin: 0, isTextBox: true });
    }
    s.addText("A PTM site is to the proteome what a variant call is to the genome: a position, a change, and the evidence for it.", {
      x: 0.6, y: 6.2, w: 12.1, h: 0.5, fontFace: BODY, fontSize: 16, italic: true, color: C.indigo, margin: 0, isTextBox: true,
    });
    s.addNotes("The working group's question is at the level of proteoforms and PTMs, not just protein abundance, so the repository keeps that level of detail.");
  }

  // 5. Delivered so far: stat callouts ------------------------------------------------------------
  {
    const s = pres.addSlide();
    s.background = { color: C.white };
    title(s, "Delivered so far");
    const stats = [
      ["10", "public datasets", C.teal],
      ["204", "raw files searched", C.indigo],
      ["4.45M", "MS2 spectra", C.magenta],
      ["2.16M", "peptide-spectrum matches at 1% FDR", C.amber],
      ["9,236", "proteins identified (4,112 in 3+ datasets)", C.green],
      ["118K", "PTM sites, 130 kinds of modification", C.teal],
    ];
    const cw = 3.85, ch = 2.05, gx = 0.3, gy = 0.3, x0 = 0.6, y0 = 1.45;
    for (let i = 0; i < stats.length; i++) {
      const [num, label, col] = stats[i];
      const x = x0 + (i % 3) * (cw + gx), y = y0 + Math.floor(i / 3) * (ch + gy);
      s.addShape("roundRect", { x, y, w: cw, h: ch, fill: { color: C.card }, line: { color: "E4E1EA" }, rectRadius: 0.1 });
      s.addText(num, { x: x + 0.3, y: y + 0.2, w: cw - 0.6, h: 1.05, fontFace: HEAD, fontSize: 54, bold: true, color: col, margin: 0, isTextBox: true });
      s.addText(label, { x: x + 0.3, y: y + 1.3, w: cw - 0.6, h: 0.6, fontFace: BODY, fontSize: 15, color: C.ink, valign: "top", margin: 0, isTextBox: true });
    }
    s.addText("Preview numbers from catalog f656bfc22cf1f675, built before the current re-processing. They will change, and each release is cited by its catalog id.", {
      x: 0.6, y: 6.35, w: 12.1, h: 0.55, fontFace: BODY, fontSize: 12, color: C.muted, margin: 0, isTextBox: true,
    });
    s.addNotes("These are the figures on the public website's front page today. Proteins counted exclude decoys and contaminants.");
  }

  // 6. The rule: define / run / store / consume ----------------------------------------------
  {
    const s = pres.addSlide();
    s.background = { color: C.white };
    title(s, "One rule for a network of projects");
    const verbs = [
      [fa.FaLightbulb, C.teal, "DEFINE", "The partner that owns the science writes the model, the definition and the version."],
      [fa.FaPlay, C.indigo, "RUN", "Wherever the code executes: inside the search (aging), or on stored results (dataRepo)."],
      [fa.FaDatabase, C.magenta, "STORE & SERVE", "dataRepo keeps every output with its engine version, inputs and definition."],
      [fa.FaQuestionCircle, C.amber, "CONSUME", "aging asks the biological questions and owns its own science."],
    ];
    const w = 2.75, gap = 0.37, x0 = 0.6, y = 1.55;
    for (let i = 0; i < verbs.length; i++) {
      const [ic, col, head, body] = verbs[i];
      const x = x0 + i * (w + gap);
      s.addShape("roundRect", { x, y, w, h: 2.95, fill: { color: C.card }, line: { color: "E4E1EA" }, rectRadius: 0.12 });
      await badge(s, ic, x + (w - 0.8) / 2, y + 0.25, 0.8, col);
      s.addText(head, { x: x + 0.15, y: y + 1.2, w: w - 0.3, h: 0.45, fontFace: HEAD, fontSize: 17, bold: true, color: col, align: "center", margin: 0, isTextBox: true });
      s.addText(body, { x: x + 0.2, y: y + 1.7, w: w - 0.4, h: 1.15, fontFace: BODY, fontSize: 13.5, color: C.ink, align: "center", valign: "top", margin: 0, isTextBox: true });
      if (i < verbs.length - 1) {
        s.addShape("rightArrow", { x: x + w + 0.06, y: y + 1.25, w: gap - 0.12, h: 0.4, fill: { color: "B9B7C9" }, line: { color: "B9B7C9" } });
      }
    }
    s.addShape("roundRect", { x: 0.6, y: 4.8, w: 12.1, h: 1.55, fill: { color: C.tint }, line: { color: C.tint }, rectRadius: 0.12 });
    s.addText([
      { text: "Why it matters. ", options: { bold: true, color: C.indigo } },
      { text: "Engines such as go, logs and ptmQtl are generic: they work for any study, so none of them knows which study to run for, and none runs itself. Without an owner for each step, the chain breaks silently: a missing link gives an empty answer, not an error. dataRepo is the owner for running engines on stored data." },
    ], { x: 0.9, y: 4.95, w: 11.5, h: 1.25, fontFace: BODY, fontSize: 15, color: C.ink, valign: "middle", margin: 0, isTextBox: true });
    s.addText("Proposed in a responsibilities charter, now with all eight projects for sign-off.", {
      x: 0.6, y: 6.6, w: 12.1, h: 0.4, fontFace: BODY, fontSize: 12, color: C.muted, margin: 0, isTextBox: true,
    });
    s.addNotes(
      "The user's instruction behind this: no critical task should slip through the cracks between projects with each one thinking it is the other's responsibility. " +
      "dataRepo never defines science, but it does run the released versions of engines on the stored data, pinned and recorded."
    );
  }

  // 7. What dataRepo does with each partner ---------------------------------------------------
  {
    const s = pres.addSlide();
    s.background = { color: C.white };
    title(s, "What dataRepo will do with each partner");
    const partners = [
      [fa.FaSitemap, C.teal, "go", "Organelle map", "RUN (to be confirmed) · STORE",
        "Store each protein's organelle assignment from Gene Ontology, so any result can be grouped by organelle."],
      [fa.FaDna, C.indigo, "logs", "Gene identity and orthology", "RUN · STORE",
        "Run its gene resolver on each searched database, so gene names are checked and species can be compared."],
      [fa.FaProjectDiagram, C.magenta, "ptmQtl", "PTM statistics", "RUN · STORE",
        "Run its models on the stored data: which PTM sites change with age or other traits, and which occur together."],
      [fa.FaCrosshairs, C.amber, "phred", "Localization confidence", "STORE",
        "Runs inside the search. dataRepo stores, per site, the confidence that a PTM sits on that residue."],
      [fa.FaClipboardList, C.green, "sdrf", "Sample metadata", "STORE",
        "Store each sample's age, sex and tissue, with ages put on one scale by sdrf's normalizer."],
      [fa.FaBalanceScale, C.teal, "QuantProject", "Quantification and definitions", "STORE",
        "Every number stored carries the id of its definition in QuantProject's registry."],
      [fa.FaPython, C.indigo, "pyMzLib", "Python bridge to mzLib", "READ · CALL",
        "Read every search file through it, and call each engine's released code through it."],
      [fa.FaPlus, C.magenta, "and more", "pride · qc · pep · localization", "PARTNERS",
        "PRIDE access, quality reports, better error rates in MetaMorpheus, site-level false localization rates."],
    ];
    const cw = 2.84, ch = 2.45, gx = 0.25, gy = 0.25, x0 = 0.6, y0 = 1.45;
    for (let i = 0; i < partners.length; i++) {
      const [ic, col, name, what, verbs, body] = partners[i];
      const x = x0 + (i % 4) * (cw + gx), y = y0 + Math.floor(i / 4) * (ch + gy);
      s.addShape("roundRect", { x, y, w: cw, h: ch, fill: { color: C.card }, line: { color: "E4E1EA" }, rectRadius: 0.1 });
      await badge(s, ic, x + 0.2, y + 0.2, 0.6, col);
      s.addText([
        { text: name, options: { fontFace: HEAD, fontSize: 16, bold: true, color: C.ink, breakLine: true } },
        { text: what, options: { fontFace: BODY, fontSize: 11.5, color: C.muted } },
      ], { x: x + 0.92, y: y + 0.15, w: cw - 1.05, h: 0.75, valign: "middle", margin: 0, isTextBox: true });
      s.addText(verbs, { x: x + 0.2, y: y + 0.98, w: cw - 0.4, h: 0.3, fontFace: HEAD, fontSize: 10.5, bold: true, color: col, margin: 0, isTextBox: true });
      s.addText(body, { x: x + 0.2, y: y + 1.3, w: cw - 0.4, h: 1.05, fontFace: BODY, fontSize: 12.5, color: C.ink, valign: "top", margin: 0, isTextBox: true });
    }
    s.addNotes(
      "RUN means dataRepo executes the partner's released code on the stored data and records the version. " +
      "STORE means the partner's output reaches dataRepo from elsewhere, usually from inside the search, and dataRepo keeps it with provenance. " +
      "localization is phred's boundary partner and is not yet a party to the charter."
    );
  }

  // 8. Built for AI agents -------------------------------------------------------------------
  {
    const s = pres.addSlide();
    s.background = { color: C.white };
    title(s, "Built for AI agents first, and honest with them");
    // Left: example questions.
    s.addShape("roundRect", { x: 0.6, y: 1.5, w: 5.6, h: 4.9, fill: { color: C.tint }, line: { color: C.tint }, rectRadius: 0.12 });
    await badge(s, fa.FaRobot, 0.9, 1.8, 0.75, C.indigo);
    s.addText("An agent can ask", { x: 1.8, y: 1.8, w: 4.2, h: 0.75, fontFace: HEAD, fontSize: 20, bold: true, color: C.ink, valign: "middle", margin: 0, isTextBox: true });
    s.addText([
      { text: "Which datasets detect this protein at 1% FDR?", options: { bullet: true, breakLine: true } },
      { text: "Which PTM sites were seen on it, and in how many datasets?", options: { bullet: true, breakLine: true } },
      { text: "How was this number calculated, and from which files?", options: { bullet: true } },
    ], { x: 0.95, y: 2.8, w: 5.0, h: 2.6, fontFace: BODY, fontSize: 16, color: C.ink, paraSpaceAfter: 10, valign: "top", margin: 0, isTextBox: true });
    s.addText("Through the Model Context Protocol, the standard way AI assistants call tools.", {
      x: 0.95, y: 5.45, w: 5.0, h: 0.7, fontFace: BODY, fontSize: 13, italic: true, color: C.muted, margin: 0, isTextBox: true,
    });
    // Right: guardrails.
    const rules = [
      [fa.FaBookmark, C.teal, "Every answer names the catalog version it came from", "so it can be cited and reproduced."],
      [fa.FaBan, C.magenta, "\"No data\" is never reported as \"zero\"", "An empty table says nothing was delivered."],
      [fa.FaExclamationTriangle, C.amber, "Known problems travel with each dataset", "such as a low identification rate or missing sample metadata."],
      [fa.FaShieldAlt, C.green, "Nothing is invented to fill a gap", "Bovine albumin, a lab reagent, is flagged and never counted as human."],
    ];
    let y = 1.55;
    for (const [ic, col, head, body] of rules) {
      await badge(s, ic, 6.7, y, 0.65, col);
      s.addText([
        { text: head, options: { fontFace: HEAD, fontSize: 15, bold: true, color: C.ink, breakLine: true } },
        { text: body, options: { fontFace: BODY, fontSize: 13.5, color: C.muted } },
      ], { x: 7.55, y: y - 0.05, w: 5.2, h: 1.05, valign: "top", margin: 0, isTextBox: true });
      y += 1.22;
    }
    s.addNotes(
      "The main users are AI agents. The design goal is zero confidently wrong answers: an agent that cannot answer should say so, rather than answer from the wrong table."
    );
  }

  // 7. Where it stands ------------------------------------------------------------------------
  {
    const s = pres.addSlide();
    s.background = { color: C.white };
    title(s, "Where it stands, and what comes next");
    const cols = [
      ["Working today", C.green, fa.FaCheckCircle, [
        "Ingest of each dataset, with counts checked against the search engine",
        "A single queryable catalog across datasets",
        "An AI agent server",
        "A public website, live as a preview",
      ]],
      ["Next", C.indigo, fa.FaArrowRight, [
        "Organelle assignments (go) and sample ages (sdrf)",
        "Checked gene identity, run by dataRepo (logs)",
        "PTM-trait statistics, run by dataRepo (ptmQtl)",
        "Per-site localization confidence (phred)",
        "Age effects per protein and PTM site (aging)",
        "Citable releases with a DOI, and permanent hosting",
      ]],
    ];
    for (let i = 0; i < cols.length; i++) {
      const [head, col, ic, items] = cols[i];
      const x = 0.6 + i * 6.25;
      s.addShape("roundRect", { x, y: 1.5, w: 5.95, h: 4.6, fill: { color: C.card }, line: { color: "E4E1EA" }, rectRadius: 0.12 });
      await badge(s, ic, x + 0.35, 1.8, 0.7, col);
      s.addText(head, { x: x + 1.25, y: 1.8, w: 4.4, h: 0.7, fontFace: HEAD, fontSize: 21, bold: true, color: C.ink, valign: "middle", margin: 0, isTextBox: true });
      s.addText(items.map((t, j) => ({ text: t, options: { bullet: true, breakLine: j < items.length - 1 } })), {
        x: x + 0.4, y: 2.7, w: 5.2, h: 3.25, fontFace: BODY, fontSize: 15, color: C.ink, paraSpaceAfter: 7, valign: "top", margin: 0, isTextBox: true,
      });
    }
    s.addText("The working group's own question, whether organelles age at different rates, needs the \"Next\" column.", {
      x: 0.6, y: 6.35, w: 12.1, h: 0.5, fontFace: BODY, fontSize: 15, italic: true, color: C.indigo, margin: 0, isTextBox: true,
    });
    s.addNotes("Each item in the Next column is owned by a partner project. dataRepo stores and serves; it does not define the science.");
  }

  // 8. Closing -------------------------------------------------------------------------------
  {
    const s = pres.addSlide();
    s.background = { color: C.night };
    s.addText("See it for yourself", {
      x: 0.8, y: 1.5, w: 11.5, h: 1.0, fontFace: HEAD, fontSize: 44, bold: true, color: C.white, margin: 0, isTextBox: true,
    });
    const links = [
      [fa.FaGlobe, C.teal, "Website", "trishorts.github.io/aging-pipeline"],
      [fa.FaGithub, C.indigo, "Code", "github.com/trishorts/dataRepo  ·  github.com/trishorts/aging-pipeline"],
      [fa.FaComments, C.magenta, "Questions", "Open an issue on aging-pipeline"],
    ];
    let y = 3.0;
    for (const [ic, col, head, body] of links) {
      await badge(s, ic, 0.8, y, 0.75, col);
      s.addText([
        { text: head, options: { fontFace: HEAD, fontSize: 18, bold: true, color: C.white, breakLine: true } },
        { text: body, options: { fontFace: BODY, fontSize: 16, color: C.lav } },
      ], { x: 1.8, y: y - 0.02, w: 10.5, h: 0.85, valign: "middle", margin: 0, isTextBox: true });
      y += 1.15;
    }
    s.addNotes("Everything shown is public: the website, the code, and soon the data files with a DOI.");
  }

  await pres.writeFile({ fileName: OUT });
  console.log("wrote", OUT);
})();
