import { ZipArchive } from './zip';

/**
 * DOCX → 可展示的 HTML（无第三方依赖）。
 *
 * 只处理简历里真正会用到的结构：段落、加粗/斜体/下划线/字号/颜色、标题样式、
 * 项目符号列表、表格、内嵌图片，以及常见的 `w:sdt` 内容控件包装。
 * 输出只包含本文件生成的标签与转义后的文本，不解析文档里的任何脚本或外部链接。
 */

const NS = {
  w: 'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
  r: 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
  a: 'http://schemas.openxmlformats.org/drawingml/2006/main',
  wp: 'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing',
  v: 'urn:schemas-microsoft-com:vml',
} as const;

/** 1 EMU = 1/9525 px（96 DPI） */
const EMU_PER_PX = 9525;

interface RenderContext {
  zip: ZipArchive;
  rels: Map<string, string>;
}

function escapeHtml(text: string): string {
  return text.replace(/[&<>"']/g, (ch) => {
    switch (ch) {
      case '&':
        return '&amp;';
      case '<':
        return '&lt;';
      case '>':
        return '&gt;';
      case '"':
        return '&quot;';
      default:
        return '&#39;';
    }
  });
}

function directChild(parent: Element | null | undefined, ns: string, local: string): Element | null {
  if (!parent) return null;
  for (const child of Array.from(parent.children)) {
    if (child.localName === local && child.namespaceURI === ns) return child;
  }
  return null;
}

function wVal(el: Element | null): string | null {
  return el ? el.getAttributeNS(NS.w, 'val') : null;
}

function flag(el: Element | null): boolean {
  if (!el) return false;
  const value = wVal(el);
  return value === null || value === 'true' || value === '1' || value === 'on';
}

function headingLevel(styleId: string): 2 | 3 | 4 | null {
  const id = styleId.trim().toLowerCase();
  if (!id) return null;
  if (/title|标题|题目/.test(id)) return 2;
  const matched = /heading\s*([1-6])/.exec(id) ?? /标题\s*([1-6])/.exec(id) ?? /^([1-6])$/.exec(id);
  if (!matched) return null;
  const level = Number(matched[1]);
  if (level <= 1) return 2;
  return level === 2 ? 3 : 4;
}

function resolveTarget(target: string): string | null {
  if (/^[a-z]+:/i.test(target)) return null; // 外链图片不内联
  if (target.startsWith('/')) return target.slice(1);
  const stack: string[] = [];
  for (const part of `word/${target}`.split('/')) {
    if (part === '..') stack.pop();
    else if (part && part !== '.') stack.push(part);
  }
  return stack.join('/');
}

function mimeOf(path: string): string | null {
  const ext = path.slice(path.lastIndexOf('.') + 1).toLowerCase();
  switch (ext) {
    case 'png':
      return 'image/png';
    case 'jpg':
    case 'jpeg':
      return 'image/jpeg';
    case 'gif':
      return 'image/gif';
    case 'bmp':
      return 'image/bmp';
    case 'webp':
      return 'image/webp';
    default:
      return null; // EMF/WMF/TIFF 等浏览器无法直接显示，跳过
  }
}

function toBase64(bytes: Uint8Array): string {
  let binary = '';
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunk));
  }
  return btoa(binary);
}

function stripTags(html: string): string {
  return html.replace(/<[^>]*>/g, '');
}

async function readRels(zip: ZipArchive): Promise<Map<string, string>> {
  const map = new Map<string, string>();
  const xml = await zip.text('word/_rels/document.xml.rels');
  if (!xml) return map;
  const doc = new DOMParser().parseFromString(xml, 'application/xml');
  for (const node of Array.from(doc.getElementsByTagName('Relationship'))) {
    const id = node.getAttribute('Id');
    const target = node.getAttribute('Target');
    const mode = node.getAttribute('TargetMode');
    if (!id || !target || mode === 'External') continue;
    map.set(id, target);
  }
  return map;
}

async function renderImage(node: Element, ctx: RenderContext): Promise<string> {
  const blip = node.getElementsByTagNameNS(NS.a, 'blip')[0];
  let relId = blip?.getAttributeNS(NS.r, 'embed') ?? null;
  if (!relId) {
    const imagedata = node.getElementsByTagNameNS(NS.v, 'imagedata')[0];
    relId = imagedata?.getAttributeNS(NS.r, 'id') ?? null;
  }
  if (!relId) return '';

  const target = ctx.rels.get(relId);
  if (!target) return '';
  const path = resolveTarget(target);
  if (!path) return '';

  const mime = mimeOf(path);
  if (!mime) return '';

  const data = await ctx.zip.get(path);
  if (!data || data.length === 0) return '';

  const extent = node.getElementsByTagNameNS(NS.wp, 'extent')[0];
  const cx = Number(extent?.getAttribute('cx') ?? 0);
  const cy = Number(extent?.getAttribute('cy') ?? 0);
  const width = cx > 0 ? Math.round(cx / EMU_PER_PX) : 0;
  const height = cy > 0 ? Math.round(cy / EMU_PER_PX) : 0;
  const size =
    width > 0 ? ` style="width:${Math.min(width, 640)}px${height > 0 ? `;height:${height}px` : ';height:auto'}"` : '';

  return `<img class="docx-img" src="data:${mime};base64,${toBase64(data)}" alt="简历图片"${size} />`;
}

async function renderRun(run: Element, ctx: RenderContext): Promise<string> {
  const rPr = directChild(run, NS.w, 'rPr');
  const chunks: string[] = [];

  for (const node of Array.from(run.children)) {
    switch (node.localName) {
      case 't':
        chunks.push(escapeHtml(node.textContent ?? ''));
        break;
      case 'tab':
        chunks.push('<span class="docx-tab"></span>');
        break;
      case 'br':
      case 'cr':
        chunks.push('<br />');
        break;
      case 'noBreakHyphen':
        chunks.push('-');
        break;
      case 'drawing':
      case 'pict': {
        const image = await renderImage(node, ctx);
        if (image) chunks.push(image);
        break;
      }
      default:
        break;
    }
  }

  if (chunks.length === 0) return '';

  let html = chunks.join('');
  if (flag(directChild(rPr, NS.w, 'b'))) html = `<strong>${html}</strong>`;
  if (flag(directChild(rPr, NS.w, 'i'))) html = `<em>${html}</em>`;
  if (flag(directChild(rPr, NS.w, 'u'))) html = `<span class="docx-underline">${html}</span>`;
  if (flag(directChild(rPr, NS.w, 'strike'))) html = `<span class="docx-strike">${html}</span>`;

  const styles: string[] = [];
  const size = wVal(directChild(rPr, NS.w, 'sz'));
  if (size && Number(size) > 0) styles.push(`font-size:${Number(size) / 2}pt`);
  const color = wVal(directChild(rPr, NS.w, 'color'));
  if (color && /^[0-9a-fA-F]{6}$/.test(color)) styles.push(`color:#${color}`);
  if (styles.length > 0) html = `<span style="${styles.join(';')}">${html}</span>`;

  return html;
}

function alignmentClass(jc: string | null): string {
  switch (jc) {
    case 'center':
      return ' docx-center';
    case 'right':
    case 'end':
      return ' docx-right';
    case 'both':
    case 'justify':
      return ' docx-justify';
    default:
      return '';
  }
}

async function renderParagraph(paragraph: Element, ctx: RenderContext): Promise<string> {
  const pPr = directChild(paragraph, NS.w, 'pPr');
  const styleId = wVal(directChild(pPr, NS.w, 'pStyle')) ?? '';
  const align = alignmentClass(wVal(directChild(pPr, NS.w, 'jc')));

  const numPr = directChild(pPr, NS.w, 'numPr');
  const listFromStyle = /list.?bullet|list.?number|列表段落/i.test(styleId);
  const isList = (!!numPr && wVal(directChild(numPr, NS.w, 'numId')) !== null) || listFromStyle;

  const runs = Array.from(paragraph.getElementsByTagNameNS(NS.w, 'r'));
  const inline = (await Promise.all(runs.map((run) => renderRun(run, ctx)))).join('');

  if (!stripTags(inline).trim() && !inline.includes('<img')) {
    return '<p class="docx-p docx-blank"></p>';
  }

  const heading = headingLevel(styleId);
  if (heading) return `<h${heading} class="docx-h${heading}${align}">${inline}</h${heading}>`;
  if (isList) {
    return `<div class="docx-li${align}"><span class="docx-bullet"></span><span class="docx-li-body">${inline}</span></div>`;
  }
  return `<p class="docx-p${align}">${inline}</p>`;
}

async function renderTable(table: Element, ctx: RenderContext): Promise<string> {
  const rows: string[] = [];

  for (const tr of Array.from(table.children)) {
    if (tr.localName !== 'tr' || tr.namespaceURI !== NS.w) continue;
    const cells: string[] = [];
    for (const tc of Array.from(tr.children)) {
      if (tc.localName !== 'tc' || tc.namespaceURI !== NS.w) continue;
      const tcPr = directChild(tc, NS.w, 'tcPr');
      const span = Number(wVal(directChild(tcPr, NS.w, 'gridSpan')) ?? 1) || 1;
      const content = await renderBlocks(tc, ctx);
      cells.push(`<td${span > 1 ? ` colspan="${span}"` : ''}>${content}</td>`);
    }
    if (cells.length > 0) rows.push(`<tr>${cells.join('')}</tr>`);
  }

  if (rows.length === 0) return '';
  return `<table class="docx-table"><tbody>${rows.join('')}</tbody></table>`;
}

async function renderBlocks(container: Element, ctx: RenderContext): Promise<string> {
  const parts: string[] = [];
  for (const node of Array.from(container.children)) {
    if (node.namespaceURI !== NS.w) continue;
    switch (node.localName) {
      case 'p':
        parts.push(await renderParagraph(node, ctx));
        break;
      case 'tbl':
        parts.push(await renderTable(node, ctx));
        break;
      case 'sdt': {
        const content = directChild(node, NS.w, 'sdtContent');
        if (content) parts.push(await renderBlocks(content, ctx));
        break;
      }
      default:
        break;
    }
  }
  return parts.join('');
}

/** DOCX（ArrayBuffer）→ 预览用 HTML；无法解析时抛错，由调用方降级为「下载查看」 */
export async function docxToHtml(buffer: ArrayBuffer): Promise<string> {
  if (!ZipArchive.isZip(buffer)) throw new Error('文件不是有效的 DOCX');

  const zip = new ZipArchive(buffer);
  const xml = await zip.text('word/document.xml');
  if (!xml) throw new Error('DOCX 缺少正文');

  const doc = new DOMParser().parseFromString(xml, 'application/xml');
  if (doc.getElementsByTagName('parsererror').length > 0) throw new Error('DOCX 正文无法解析');

  const body = doc.getElementsByTagNameNS(NS.w, 'body')[0];
  if (!body) throw new Error('DOCX 正文为空');

  const rels = await readRels(zip);
  const html = await renderBlocks(body, { zip, rels });

  if (!stripTags(html).trim() && !html.includes('<img')) {
    throw new Error('DOCX 中没有可展示的内容');
  }
  return html;
}
