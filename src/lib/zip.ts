/**
 * 最小 ZIP 读取器（仅覆盖 .docx 需要的场景）。
 *
 * 简历预览在浏览器里直接解析 DOCX，不依赖任何第三方库：DOCX 本质是 ZIP，
 * 只要读出 `word/document.xml` 与内嵌图片即可，无需解压整个包。
 * 解压使用浏览器原生的 DecompressionStream('deflate-raw')。
 */

interface ZipEntryMeta {
  name: string;
  /** 0 = 存储，8 = deflate */
  method: number;
  compressedSize: number;
  localOffset: number;
}

const EOCD_SIG = 0x06054b50;
const CENTRAL_SIG = 0x02014b50;
const LOCAL_SIG = 0x04034b50;

export class ZipArchive {
  private readonly view: DataView;
  private readonly entries = new Map<string, ZipEntryMeta>();
  private readonly cache = new Map<string, Uint8Array>();
  private readonly order: ZipEntryMeta[] = [];

  constructor(private readonly buffer: ArrayBuffer) {
    this.view = new DataView(buffer);
    this.readCentralDirectory();
  }

  static isZip(buffer: ArrayBuffer): boolean {
    return buffer.byteLength >= 4 && new DataView(buffer).getUint32(0, true) === LOCAL_SIG;
  }

  names(): string[] {
    return [...this.entries.keys()];
  }

  has(name: string): boolean {
    return this.entries.has(name);
  }

  /** 读取并解压一个条目，不存在时返回 null */
  async get(name: string): Promise<Uint8Array | null> {
    const cached = this.cache.get(name);
    if (cached) return cached;
    const entry = this.entries.get(name);
    if (!entry) return null;

    const data = await this.extract(entry);
    this.cache.set(name, data);
    return data;
  }

  async text(name: string): Promise<string | null> {
    const data = await this.get(name);
    if (!data) return null;
    return new TextDecoder('utf-8').decode(data);
  }

  private readCentralDirectory(): void {
    const { view, buffer } = this;
    let eocd = -1;
    const min = Math.max(0, view.byteLength - 22 - 0xffff);
    for (let i = view.byteLength - 22; i >= min; i -= 1) {
      if (view.getUint32(i, true) === EOCD_SIG) {
        eocd = i;
        break;
      }
    }
    if (eocd < 0) throw new Error('文件不是有效的 DOCX（ZIP 结构缺失）');

    const count = view.getUint16(eocd + 10, true);
    const cdOffset = view.getUint32(eocd + 16, true);
    const decoder = new TextDecoder('utf-8');

    let p = cdOffset;
    for (let i = 0; i < count; i += 1) {
      if (p + 46 > buffer.byteLength || view.getUint32(p, true) !== CENTRAL_SIG) break;
      const method = view.getUint16(p + 10, true);
      const compressedSize = view.getUint32(p + 20, true);
      const nameLen = view.getUint16(p + 28, true);
      const extraLen = view.getUint16(p + 30, true);
      const commentLen = view.getUint16(p + 32, true);
      const localOffset = view.getUint32(p + 42, true);
      const name = decoder.decode(new Uint8Array(buffer, p + 46, nameLen));

      const entry: ZipEntryMeta = { name, method, compressedSize, localOffset };
      this.entries.set(name, entry);
      this.order.push(entry);

      p += 46 + nameLen + extraLen + commentLen;
    }

    // 部分写入器使用数据描述符（bit 3），中央目录里的压缩长度可能是 0，
    // 此时用下一个条目的本地头偏移兜底推算长度。
    this.order.forEach((entry, index) => {
      if (entry.compressedSize !== 0) return;
      const next = this.order[index + 1];
      if (!next) return;
      const localNameLen = view.getUint16(entry.localOffset + 26, true);
      const localExtraLen = view.getUint16(entry.localOffset + 28, true);
      const start = entry.localOffset + 30 + localNameLen + localExtraLen;
      entry.compressedSize = Math.max(0, next.localOffset - start);
    });
  }

  private async extract(entry: ZipEntryMeta): Promise<Uint8Array> {
    const { view, buffer } = this;
    if (view.getUint32(entry.localOffset, true) !== LOCAL_SIG) {
      throw new Error(`DOCX 条目损坏：${entry.name}`);
    }
    const nameLen = view.getUint16(entry.localOffset + 26, true);
    const extraLen = view.getUint16(entry.localOffset + 28, true);
    const start = entry.localOffset + 30 + nameLen + extraLen;
    const raw = new Uint8Array(buffer, start, entry.compressedSize);

    if (entry.method === 0) return raw.slice();
    if (entry.method !== 8) throw new Error(`不支持的压缩方式：${entry.method}`);

    const stream = new Response(raw).body!.pipeThrough(new DecompressionStream('deflate-raw'));
    return new Uint8Array(await new Response(stream).arrayBuffer());
  }
}
