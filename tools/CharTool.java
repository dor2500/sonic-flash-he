import com.jpexs.decompiler.flash.SWF;
import com.jpexs.decompiler.flash.tags.*;
import com.jpexs.decompiler.flash.tags.base.ShapeTag;
import com.jpexs.decompiler.flash.types.*;
import com.jpexs.decompiler.flash.types.shaperecords.*;

import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.MessageDigest;
import java.util.*;

/**
 * New characters for the SWF (spec written by tools/make_chars.py).
 *   chars <in.swf> <out.swf> <spec.txt> <newimages.txt>
 * spec blocks:
 *   clone <srcSpriteId> <exportName>      deep copy of a sprite tree, exported under a new linkage name
 *   frame <spriteId> <label> <refLabel>   new labelled frame = copy of the refLabel frame
 *   img <origBitmapId> <png> <dx> <dy>    inside the block: that bitmap becomes png, its top-left moved by (dx, dy) px
 *   end
 * newimages.txt: "<newBitmapId>\t<png>" (1x sources for the HD pass).
 */
public class CharTool {
    static SWF swf;
    static int nextId;
    static Map<String, Integer> pngIds = new HashMap<>();
    static StringBuilder newImages = new StringBuilder();
    static List<Tag> pending = new ArrayList<>();

    static class Img { String png; int dx, dy; }

    public static void main(String[] a) throws Exception {
        try (InputStream is = new BufferedInputStream(new FileInputStream(a[1]))) {
            swf = new SWF(is, false);
        }
        nextId = swf.getNextCharacterId();
        List<String> lines = Files.readAllLines(Paths.get(a[3]), StandardCharsets.UTF_8);
        String[] head = null;
        Map<Integer, Img> imgs = new HashMap<>();
        int nClone = 0, nFrame = 0;
        for (String line : lines) {
            String[] p = line.trim().split("\t");
            if (p[0].isEmpty() || p[0].startsWith("#")) continue;
            switch (p[0]) {
                case "clone": case "frame": head = p; imgs = new HashMap<>(); break;
                case "img": {
                    Img im = new Img(); im.png = p[2]; im.dx = Integer.parseInt(p[3]); im.dy = Integer.parseInt(p[4]);
                    imgs.put(Integer.parseInt(p[1]), im);
                    break;
                }
                case "end":
                    if (head[0].equals("clone")) { cloneSprite(Integer.parseInt(head[1]), head[2], imgs); nClone++; }
                    else { addFrame(Integer.parseInt(head[1]), head[2], head[3], imgs); nFrame++; }
                    break;
                default: throw new RuntimeException("bad spec line: " + line);
            }
        }
        // all new definitions go right before the first ShowFrame of the main timeline (loaded first, before any use)
        List<Tag> tags = new ArrayList<>(swf.getTags().toArrayList());
        int at = 0;
        while (!(tags.get(at) instanceof ShowFrameTag)) at++;
        for (Tag t : pending) swf.addTag(at++, t);
        swf.updateCharacters();
        swf.clearAllCache();
        try (OutputStream os = new BufferedOutputStream(new FileOutputStream(a[2]))) {
            swf.saveTo(os);
        }
        Files.write(Paths.get(a[4]), newImages.toString().getBytes(StandardCharsets.UTF_8));
        System.out.println("chars: " + nClone + " clones, " + nFrame + " frames, " + pngIds.size() + " new bitmaps, next id " + nextId);
    }

    static Tag tag(int id) { return swf.getCharacter(id); }

    /** a new bitmap for a png (identical files share one bitmap) */
    static int bitmap(String png) throws Exception {
        byte[] data = Files.readAllBytes(Paths.get(png));
        String key = Base64.getEncoder().encodeToString(MessageDigest.getInstance("SHA-1").digest(data));
        Integer id = pngIds.get(key);
        if (id != null) return id;
        DefineBitsLossless2Tag b = new DefineBitsLossless2Tag(swf);
        b.setCharacterId(nextId);
        b.setImage(data);
        b.setModified(true);
        pending.add(b);
        pngIds.put(key, nextId);
        newImages.append(nextId).append('\t').append(png).append('\n');
        return nextId++;
    }

    static List<FILLSTYLE> bitmapFills(ShapeTag st) {
        List<FILLSTYLE> out = new ArrayList<>();
        List<FILLSTYLEARRAY> arrs = new ArrayList<>();
        arrs.add(st.shapes.fillStyles);
        for (SHAPERECORD r : st.shapes.shapeRecords)
            if (r instanceof StyleChangeRecord && ((StyleChangeRecord) r).stateNewStyles) arrs.add(((StyleChangeRecord) r).fillStyles);
        for (FILLSTYLEARRAY arr : arrs)
            if (arr != null && arr.fillStyles != null)
                for (FILLSTYLE fs : arr.fillStyles) if (fs.fillStyleType >= 0x40 && fs.fillStyleType <= 0x43) out.add(fs);
        return out;
    }

    /** copy of a shape; a replaced bitmap gets a rectangle sized to the new png at the shifted position */
    static ShapeTag cloneShape(ShapeTag src, Map<Integer, Img> imgs) throws Exception {
        ShapeTag st = (ShapeTag) src.cloneTag();
        st.setCharacterId(nextId++);
        for (FILLSTYLE fs : bitmapFills(st)) {
            Img im = imgs.get(fs.bitmapId);
            if (im == null) continue;
            java.awt.image.BufferedImage bi = javax.imageio.ImageIO.read(new File(im.png));
            fs.bitmapId = bitmap(im.png);
            MATRIX m = fs.bitmapMatrix;
            double sx = m.hasScale ? m.scaleX : 1, sy = m.hasScale ? m.scaleY : 1;
            int x0 = m.translateX + (int) Math.round(im.dx * sx), y0 = m.translateY + (int) Math.round(im.dy * sy);
            int w = (int) Math.round(bi.getWidth() * sx), h = (int) Math.round(bi.getHeight() * sy);
            m.translateX = x0; m.translateY = y0;
            m.hasRotate = false;
            fs.fillStyleType = 0x43; // clipped, not smoothed (pixel art)
            rect(st, x0, y0, w, h);
        }
        st.setModified(true);
        return st;
    }

    static void rect(ShapeTag st, int x0, int y0, int w, int h) {
        StyleChangeRecord sc = null;
        for (SHAPERECORD r : st.shapes.shapeRecords) if (r instanceof StyleChangeRecord) { sc = ((StyleChangeRecord) r).clone(); break; }
        sc.stateMoveTo = true; sc.moveDeltaX = x0; sc.moveDeltaY = y0;
        sc.calculateBits();
        List<SHAPERECORD> recs = new ArrayList<>();
        recs.add(sc);
        int[][] d = {{w, 0}, {0, h}, {-w, 0}, {0, -h}};
        for (int[] e : d) {
            StraightEdgeRecord r = new StraightEdgeRecord();
            r.deltaX = e[0]; r.deltaY = e[1];
            r.generalLineFlag = false; r.vertLineFlag = e[0] == 0;
            r.calculateBits();
            recs.add(r);
        }
        recs.add(new EndShapeRecord());
        st.shapes.shapeRecords = recs;
        st.shapeBounds = new RECT(x0, x0 + w, y0, y0 + h);
    }

    static void cloneSprite(int srcId, String name, Map<Integer, Img> imgs) throws Exception {
        // closure of sprites and shapes, children first
        List<Integer> order = new ArrayList<>();
        visit(srcId, new HashSet<>(), order);
        Map<Integer, Integer> idMap = new HashMap<>();
        for (int id : order) {
            Tag t = tag(id);
            if (t instanceof ShapeTag) {
                ShapeTag st = cloneShape((ShapeTag) t, imgs);
                idMap.put(id, st.getCharacterId());
                pending.add(st);
            } else {
                DefineSpriteTag sp = (DefineSpriteTag) ((DefineSpriteTag) t).cloneTag();
                sp.setCharacterId(nextId++);
                for (Tag s : sp.getTags()) {
                    if (s instanceof PlaceObject2Tag) {
                        PlaceObject2Tag po = (PlaceObject2Tag) s;
                        if (po.placeFlagHasCharacter && idMap.containsKey(po.characterId)) po.characterId = idMap.get(po.characterId);
                    }
                    s.setModified(true);
                }
                sp.setModified(true);
                idMap.put(id, sp.getCharacterId());
                pending.add(sp);
            }
        }
        ExportAssetsTag ex = new ExportAssetsTag(swf);
        ex.tags = new ArrayList<>(List.of(idMap.get(srcId)));
        ex.names = new ArrayList<>(List.of(name));
        ex.setModified(true);
        pending.add(ex);
    }

    static void visit(int id, Set<Integer> seen, List<Integer> order) {
        if (!seen.add(id)) return;
        Tag t = tag(id);
        if (t instanceof DefineSpriteTag) {
            for (Tag s : ((DefineSpriteTag) t).getTags())
                if (s instanceof PlaceObject2Tag && ((PlaceObject2Tag) s).placeFlagHasCharacter) visit(((PlaceObject2Tag) s).characterId, seen, order);
            order.add(id);
        } else if (t instanceof ShapeTag) {
            order.add(id);
        }
    }

    /** display list state: depth -> merged PlaceObject2 */
    static TreeMap<Integer, PlaceObject2Tag> state(DefineSpriteTag sp, int uptoFrame) throws Exception {
        TreeMap<Integer, PlaceObject2Tag> dl = new TreeMap<>();
        int f = 1;
        for (Tag s : sp.getTags()) {
            if (s instanceof ShowFrameTag) { if (f == uptoFrame) break; f++; }
            else if (s instanceof PlaceObject2Tag) {
                PlaceObject2Tag po = (PlaceObject2Tag) s, cur = dl.get(po.depth);
                if (cur == null || po.placeFlagHasCharacter && !po.placeFlagMove) cur = (PlaceObject2Tag) po.cloneTag();
                else {
                    cur = (PlaceObject2Tag) cur.cloneTag();
                    if (po.placeFlagHasCharacter) { cur.characterId = po.characterId; cur.placeFlagHasCharacter = true; }
                    if (po.placeFlagHasMatrix) { cur.matrix = po.matrix; cur.placeFlagHasMatrix = true; }
                    if (po.placeFlagHasColorTransform) { cur.colorTransform = po.colorTransform; cur.placeFlagHasColorTransform = true; }
                    if (po.placeFlagHasRatio) { cur.ratio = po.ratio; cur.placeFlagHasRatio = true; }
                    if (po.placeFlagHasName) { cur.name = po.name; cur.placeFlagHasName = true; }
                }
                dl.put(po.depth, cur);
            } else if (s instanceof RemoveObject2Tag) dl.remove(((RemoveObject2Tag) s).depth);
            else if (s instanceof RemoveObjectTag) dl.remove(((RemoveObjectTag) s).depth);
        }
        return dl;
    }

    static void addFrame(int spriteId, String label, String ref, Map<Integer, Img> imgs) throws Exception {
        DefineSpriteTag sp = (DefineSpriteTag) tag(spriteId);
        int refFrame = 0, f = 1;
        for (Tag s : sp.getTags()) {
            if (s instanceof FrameLabelTag && ((FrameLabelTag) s).name.equals(ref)) refFrame = f;
            if (s instanceof ShowFrameTag) f++;
        }
        if (refFrame == 0) throw new RuntimeException("sprite " + spriteId + ": no label " + ref);
        TreeMap<Integer, PlaceObject2Tag> end = state(sp, Integer.MAX_VALUE), want = state(sp, refFrame);
        int at = sp.getTags().size();
        while (at > 0 && sp.getTags().get(at - 1) instanceof EndTag) at--;
        List<Tag> add = new ArrayList<>();
        FrameLabelTag fl = new FrameLabelTag(swf);
        fl.name = label;
        add.add(fl);
        for (int d : end.keySet()) {
            RemoveObject2Tag r = new RemoveObject2Tag(swf);
            r.depth = d;
            add.add(r);
        }
        for (PlaceObject2Tag po : want.values()) {
            PlaceObject2Tag n = (PlaceObject2Tag) po.cloneTag();
            n.placeFlagMove = false;
            n.placeFlagHasClipActions = false; n.clipActions = null;
            Tag c = tag(n.characterId);
            if (c instanceof ShapeTag) {
                boolean hit = false;
                for (FILLSTYLE fs : bitmapFills((ShapeTag) c)) hit |= imgs.containsKey(fs.bitmapId);
                if (hit) {
                    ShapeTag st = cloneShape((ShapeTag) c, imgs);
                    pending.add(st);
                    n.characterId = st.getCharacterId();
                }
            }
            add.add(n);
        }
        add.add(new ShowFrameTag(swf));
        for (Tag t : add) { t.setTimelined(sp); sp.addTag(at++, t); t.setModified(true); }
        sp.frameCount++;
        sp.setModified(true);
    }
}
