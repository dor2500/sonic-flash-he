import com.jpexs.decompiler.flash.SWF;
import com.jpexs.decompiler.flash.tags.DefineEditTextTag;
import com.jpexs.decompiler.flash.tags.DefineFont2Tag;
import com.jpexs.decompiler.flash.tags.DefineFontInfoTag;
import com.jpexs.decompiler.flash.tags.DefineFontTag;
import com.jpexs.decompiler.flash.tags.Tag;
import com.jpexs.decompiler.flash.tags.base.FontTag;
import com.jpexs.decompiler.flash.tags.base.MissingCharacterHandler;
import com.jpexs.decompiler.flash.tags.base.StaticTextTag;
import com.jpexs.decompiler.flash.tags.base.TextTag;

import java.awt.Font;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;

/**
 * Hebrew patcher for the SWF.
 *   dump  <in.swf> <outdir>                  - formatted text of every text tag -> <id>.txt
 *   patch <in.swf> <out.swf> <fonts.txt> <textsdir>
 * fonts.txt lines: "<fontId> <ttf path> <extra chars>" -> glyphs added to that font.
 * textsdir/<id>.txt: new formatted text (same format as dump) for that text tag.
 */
public class HeTool {
    public static void main(String[] a) throws Exception {
        SWF swf;
        try (InputStream is = new BufferedInputStream(new FileInputStream(a[1]))) {
            swf = new SWF(is, false);
        }
        if (a[0].equals("dump")) {
            Files.createDirectories(Paths.get(a[2]));
            for (Tag t : swf.getTags()) {
                if (t instanceof TextTag) {
                    TextTag tt = (TextTag) t;
                    String s = tt.getFormattedText(false).text;
                    Files.write(Paths.get(a[2], tt.getCharacterId() + ".txt"), s.getBytes(StandardCharsets.UTF_8));
                }
            }
            return;
        }
        if (a[0].equals("fills")) {
            // "<bitmapId>\t<repeat|clip>" for every bitmap used by a shape fill
            Map<Integer, String> use = new TreeMap<>();
            forEachBitmapFill(swf, (st, fs) -> use.merge(fs.bitmapId, (fs.fillStyleType & 1) == 0 ? "repeat" : "clip",
                    (x, y) -> x.equals("repeat") || y.equals("repeat") ? "repeat" : "clip"));
            StringBuilder b = new StringBuilder();
            use.forEach((k, v) -> b.append(k).append('\t').append(v).append('\n'));
            Files.write(Paths.get(a[2]), b.toString().getBytes(StandardCharsets.UTF_8));
            return;
        }
        if (a[0].equals("hd")) {
            // hd <in> <out> <dirs ";"> <factors ";">: swap bitmaps for the <id>.png upscaled copies, keep on-screen size
            String[] dirs = a[3].split(";"), ks = a[4].split(";");
            Map<Integer, Double> done = new HashMap<>();
            for (Tag t : swf.getTags()) {
                if (t instanceof com.jpexs.decompiler.flash.tags.base.ImageTag) {
                    com.jpexs.decompiler.flash.tags.base.ImageTag it = (com.jpexs.decompiler.flash.tags.base.ImageTag) t;
                    for (int d = 0; d < dirs.length; d++) {
                        Path p = Paths.get(dirs[d], it.getCharacterId() + ".png");
                        if (!Files.exists(p)) continue;
                        it.setImage(Files.readAllBytes(p));
                        it.setModified(true);
                        done.put(it.getCharacterId(), Double.parseDouble(ks[d]));
                        break;
                    }
                }
            }
            int[] n = {0};
            forEachBitmapFill(swf, (st, fs) -> {
                if (!done.containsKey(fs.bitmapId)) return;
                double k = done.get(fs.bitmapId);
                com.jpexs.decompiler.flash.types.MATRIX m = fs.bitmapMatrix;
                if (!m.hasScale) { m.hasScale = true; m.scaleX = 1; m.scaleY = 1; }
                m.scaleX /= k; m.scaleY /= k;
                if (m.hasRotate) { m.rotateSkew0 /= k; m.rotateSkew1 /= k; }
                ((Tag) st).setModified(true);
                n[0]++;
            });
            try (OutputStream os = new BufferedOutputStream(new FileOutputStream(a[2]))) {
                swf.saveTo(os);
            }
            System.out.println("hd: " + done.size() + " bitmaps, " + n[0] + " fills, saved " + a[2]);
            return;
        }
        // SWF 5 stores strings in the system ANSI code page; SWF 6+ uses UTF-8 everywhere
        swf.version = Math.max(swf.version, 6);
        swf.setCharset("UTF-8");
        // clip event flags grow from 16 to 32 bits in SWF 6: re-serialize every PlaceObject2
        markPlaceObjects(swf.getTags());
        // 1. fonts
        Map<Integer, Font> awt = new HashMap<>();
        for (String line : Files.readAllLines(Paths.get(a[3]), StandardCharsets.UTF_8)) {
            line = line.trim();
            if (line.isEmpty() || line.startsWith("#")) continue;
            String[] p = line.split("\t");
            int id = Integer.parseInt(p[0]);
            Font f = Font.createFont(Font.TRUETYPE_FONT, new File(p[1])).deriveFont(1024f);
            awt.put(id, f);
            FontTag ft = (FontTag) swf.getCharacter(id);
            // 8-bit ANSI code tables cannot hold Hebrew: switch the font to 16-bit (Unicode) codes
            if (ft instanceof DefineFont2Tag) {
                ((DefineFont2Tag) ft).fontFlagsWideCodes = true;
                ((DefineFont2Tag) ft).fontFlagsANSI = false;
            } else if (ft instanceof DefineFontTag) {
                for (Tag t : swf.getTags()) {
                    if (t instanceof DefineFontInfoTag && ((DefineFontInfoTag) t).fontID == id) {
                        ((DefineFontInfoTag) t).fontFlagsWideCodes = true;
                        ((DefineFontInfoTag) t).fontFlagsANSI = false;
                        t.setModified(true);
                    }
                }
            }
            StringBuilder chars = new StringBuilder();
            for (char c = 'א'; c <= 'ת'; c++) chars.append(c);
            if (p.length > 2) chars.append(p[2]);
            int n = 0;
            for (char c : chars.toString().toCharArray()) {
                if (!ft.containsChar(c)) {
                    if (!f.canDisplay(c)) { System.err.println("font " + id + " ttf lacks " + c); continue; }
                    ft.addCharacter(c, f);
                    n++;
                }
            }
            ft.setModified(true);
            System.out.println("font " + id + " (" + ft.getFontName() + "): +" + n + " glyphs");
        }
        MissingCharacterHandler mh = new MissingCharacterHandler() {
            @Override
            public boolean handle(TextTag textTag, FontTag font, char character) {
                Font f = awt.get(font.getCharacterId());
                if (f == null || !f.canDisplay(character)) {
                    System.err.println("missing char '" + character + "' in font " + font.getCharacterId());
                    return false;
                }
                font.addCharacter(character, f);
                return true;
            }
        };
        // 2. texts
        File[] files = new File(a[4]).listFiles((d, n) -> n.endsWith(".txt"));
        Arrays.sort(files);
        for (File file : files) {
            int id = Integer.parseInt(file.getName().replace(".txt", ""));
            TextTag tt = (TextTag) swf.getCharacter(id);
            String s = new String(Files.readAllBytes(file.toPath()), StandardCharsets.UTF_8).replace("\r\n", "\n");
            if (tt instanceof DefineEditTextTag) {
                DefineEditTextTag et = (DefineEditTextTag) tt;
                // ensure glyphs exist for the initial text
                FontTag ft = (FontTag) swf.getCharacter(et.fontId);
                String init = s.substring(s.indexOf(']') + 1);
                for (char c : init.toCharArray()) if (c >= ' ' && !ft.containsChar(c)) mh.handle(tt, ft, c);
            }
            if (!tt.setFormattedText(mh, s, null)) System.err.println("text " + id + " failed");
            tt.setModified(true);
        }
        // 3. shapes replaced by images (images.txt next to fonts.txt: "<shapeId>\t<png>", stretched to the shape bounds)
        Path imgs = Paths.get(a[3]).resolveSibling("images.txt");
        if (Files.exists(imgs)) {
            for (String line : Files.readAllLines(imgs, StandardCharsets.UTF_8)) {
                String[] p = line.trim().split("\t");
                if (p.length < 2) continue;
                com.jpexs.decompiler.flash.tags.base.ShapeTag st =
                        (com.jpexs.decompiler.flash.tags.base.ShapeTag) swf.getCharacter(Integer.parseInt(p[0]));
                new com.jpexs.decompiler.flash.importers.ShapeImporter().importImage(st, Files.readAllBytes(Paths.get(p[1])), 0, true);
                System.out.println("shape " + p[0] + " <- " + p[1]);
            }
        }
        try (OutputStream os = new BufferedOutputStream(new FileOutputStream(a[2]))) {
            swf.saveTo(os);
        }
        System.out.println("saved " + a[2]);
    }

    interface FillVisitor {
        void visit(com.jpexs.decompiler.flash.tags.base.ShapeTag st, com.jpexs.decompiler.flash.types.FILLSTYLE fs);
    }

    /** every bitmap FILLSTYLE of every shape (top-level style array + StyleChangeRecord new styles) */
    static void forEachBitmapFill(SWF swf, FillVisitor v) {
        for (Tag t : swf.getTags()) {
            if (!(t instanceof com.jpexs.decompiler.flash.tags.base.ShapeTag)) continue;
            com.jpexs.decompiler.flash.tags.base.ShapeTag st = (com.jpexs.decompiler.flash.tags.base.ShapeTag) t;
            com.jpexs.decompiler.flash.types.SHAPEWITHSTYLE sh = st.getShapes();
            List<com.jpexs.decompiler.flash.types.FILLSTYLEARRAY> arrs = new ArrayList<>();
            arrs.add(sh.fillStyles);
            for (com.jpexs.decompiler.flash.types.shaperecords.SHAPERECORD r : sh.shapeRecords) {
                if (r instanceof com.jpexs.decompiler.flash.types.shaperecords.StyleChangeRecord) {
                    com.jpexs.decompiler.flash.types.shaperecords.StyleChangeRecord sc =
                            (com.jpexs.decompiler.flash.types.shaperecords.StyleChangeRecord) r;
                    if (sc.stateNewStyles && sc.fillStyles != null) arrs.add(sc.fillStyles);
                }
            }
            for (com.jpexs.decompiler.flash.types.FILLSTYLEARRAY arr : arrs) {
                if (arr == null || arr.fillStyles == null) continue;
                for (com.jpexs.decompiler.flash.types.FILLSTYLE fs : arr.fillStyles) {
                    if (fs.fillStyleType >= 0x40 && fs.fillStyleType <= 0x43) v.visit(st, fs);
                }
            }
        }
    }

    static void markPlaceObjects(Iterable<Tag> tags) {
        for (Tag t : tags) {
            if (t instanceof com.jpexs.decompiler.flash.tags.PlaceObject2Tag) t.setModified(true);
            if (t instanceof com.jpexs.decompiler.flash.tags.DefineSpriteTag) {
                markPlaceObjects(((com.jpexs.decompiler.flash.tags.DefineSpriteTag) t).getTags());
                t.setModified(true);
            }
        }
    }
}
