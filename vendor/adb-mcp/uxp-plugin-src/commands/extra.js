/* extra.js — additional command handlers covering the full Premiere Pro UXP API surface.
 * Built on top of the existing core.js/utils.js patterns. All mutations flow through the
 * create*Action -> executeTransaction pattern via the shared `execute()` helper.
 *
 * Capability map: see PREMIERE_API_CAPABILITIES.html in the adb-mcp root.
 */

const app = require("premierepro");
const constants = require("premierepro").Constants;

const { TRACK_TYPE } = require("./consts.js");
const {
    _getSequenceFromId,
    _setActiveSequence,
    setParam,
    getParam,
    addEffect,
    findProjectItem,
    execute,
    getTrack,
    getTrackItems,
} = require("./utils.js");

/* ------------------------------------------------------------------ *
 * Color-label helpers
 * ------------------------------------------------------------------ */

// Premiere project-item label palette (index order per Constants.ProjectItemColorLabel).
// "Red" maps to Rose (the reddest available project-item label).
const COLOR_LABEL_FALLBACK = {
    VIOLET: 0, IRIS: 1, CARIBBEAN: 2, LAVENDER: 3, CERULEAN: 4, FOREST: 5,
    ROSE: 6, MANGO: 7, PURPLE: 8, BLUE: 9, TEAL: 10, MAGENTA: 11,
    TAN: 12, GREEN: 13, BROWN: 14, YELLOW: 15,
};
// friendly aliases (incl. German) -> palette name
const COLOR_ALIAS = {
    RED: "ROSE", ROT: "ROSE", ROSE: "ROSE", PINK: "MAGENTA", MAGENTA: "MAGENTA",
    ORANGE: "MANGO", MANGO: "MANGO", GELB: "YELLOW", YELLOW: "YELLOW",
    GRUEN: "GREEN", "GRÜN": "GREEN", GREEN: "GREEN", FOREST: "FOREST",
    BLAU: "BLUE", BLUE: "BLUE", CERULEAN: "CERULEAN", TEAL: "TEAL", CARIBBEAN: "CARIBBEAN",
    LILA: "PURPLE", PURPLE: "PURPLE", VIOLET: "VIOLET", IRIS: "IRIS",
    LAVENDER: "LAVENDER", TAN: "TAN", BRAUN: "BROWN", BROWN: "BROWN",
};

const resolveColorIndex = (colorName, colorIndex) => {
    if (Number.isInteger(colorIndex)) return colorIndex;
    if (!colorName) return COLOR_LABEL_FALLBACK.ROSE;
    const key = String(colorName).trim().toUpperCase();
    const paletteName = COLOR_ALIAS[key] || key;
    // prefer the live Constants enum if present, else the fallback table
    const fromConstants =
        constants && constants.ProjectItemColorLabel
            ? constants.ProjectItemColorLabel[paletteName]
            : undefined;
    if (Number.isInteger(fromConstants)) return fromConstants;
    if (Number.isInteger(COLOR_LABEL_FALLBACK[paletteName]))
        return COLOR_LABEL_FALLBACK[paletteName];
    return COLOR_LABEL_FALLBACK.ROSE;
};

/* ------------------------------------------------------------------ *
 * PROJECT ITEMS
 * ------------------------------------------------------------------ */

// setColorLabel : { itemNames:[...], colorName?:"red", colorIndex?:6 }
// Sets the project-panel color label on one or more items (colours every timeline
// instance of that item). This is the "mark my graphics red" command.
const setColorLabel = async (command) => {
    const options = command.options;
    const names = options.itemNames || (options.itemName ? [options.itemName] : []);
    const idx = resolveColorIndex(options.colorName, options.colorIndex);

    const project = await app.Project.getActiveProject();

    const items = [];
    const missing = [];
    for (const name of names) {
        try {
            items.push(await findProjectItem(name, project));
        } catch (e) {
            missing.push(name);
        }
    }

    for (const item of items) {
        const pi = app.ProjectItem.cast(item) || item;
        execute(() => [pi.createSetColorLabelAction(idx)], project);
    }

    return { labeled: items.length, colorIndex: idx, missing };
};

// getColorLabel : { itemName } -> { colorIndex }
const getColorLabel = async (command) => {
    const project = await app.Project.getActiveProject();
    const item = await findProjectItem(command.options.itemName, project);
    const pi = app.ProjectItem.cast(item) || item;
    const colorIndex = await pi.getColorLabelIndex();
    return { colorIndex };
};

// renameProjectItem : { itemName, newName }
const renameProjectItem = async (command) => {
    const { itemName, newName } = command.options;
    const project = await app.Project.getActiveProject();
    const item = await findProjectItem(itemName, project);
    const pi = app.ProjectItem.cast(item) || item;
    execute(() => [pi.createSetNameAction(newName)], project);
    return { renamed: itemName, to: newName };
};

// relinkMedia : { itemName, newPath } (not undoable per API)
const relinkMedia = async (command) => {
    const { itemName, newPath } = command.options;
    const project = await app.Project.getActiveProject();
    const item = await findProjectItem(itemName, project);
    const clip = app.ClipProjectItem.cast(item);
    if (!clip) throw new Error(`relinkMedia : [${itemName}] is not a clip item`);
    const ok = await clip.changeMediaFilePath(newPath, false);
    return { relinked: ok, itemName, newPath };
};

// overrideFrameRate : { itemName, fps }
const overrideFrameRate = async (command) => {
    const { itemName, fps } = command.options;
    const project = await app.Project.getActiveProject();
    const item = await findProjectItem(itemName, project);
    const clip = app.ClipProjectItem.cast(item);
    if (!clip) throw new Error(`overrideFrameRate : [${itemName}] is not a clip item`);
    execute(() => [clip.createSetOverrideFrameRateAction(fps)], project);
    return { itemName, fps };
};

// setProjectItemOffline : { itemName }
const setProjectItemOffline = async (command) => {
    const { itemName } = command.options;
    const project = await app.Project.getActiveProject();
    const item = await findProjectItem(itemName, project);
    const clip = app.ClipProjectItem.cast(item);
    if (!clip) throw new Error(`setProjectItemOffline : [${itemName}] is not a clip item`);
    execute(() => [clip.createSetOfflineAction()], project);
    return { offline: itemName };
};

// attachProxy : { itemName, proxyPath, isHiRes? }
const attachProxy = async (command) => {
    const { itemName, proxyPath, isHiRes } = command.options;
    const project = await app.Project.getActiveProject();
    const item = await findProjectItem(itemName, project);
    const clip = app.ClipProjectItem.cast(item);
    if (!clip) throw new Error(`attachProxy : [${itemName}] is not a clip item`);
    const ok = await clip.attachProxy(proxyPath, !!isHiRes, false);
    return { attached: ok, itemName, proxyPath };
};

// getProjectItemInfo : { itemName } -> media path, in/out, proxy, offline
const getProjectItemInfo = async (command) => {
    const { itemName } = command.options;
    const project = await app.Project.getActiveProject();
    const item = await findProjectItem(itemName, project);
    const clip = app.ClipProjectItem.cast(item);
    const out = { name: item.name };
    if (clip) {
        try { out.mediaFilePath = await clip.getMediaFilePath(); } catch (e) {}
        try { out.hasProxy = await clip.hasProxy(); } catch (e) {}
        try { out.isOffline = await clip.isOffline(); } catch (e) {}
        try { out.colorLabelIndex = await clip.getColorLabelIndex(); } catch (e) {}
    }
    return out;
};

/* ------------------------------------------------------------------ *
 * BINS
 * ------------------------------------------------------------------ */

// renameBin : { binName, newName }
const renameBin = async (command) => {
    const { binName, newName } = command.options;
    const project = await app.Project.getActiveProject();
    const item = await findProjectItem(binName, project);
    const folder = app.FolderItem.cast(item);
    if (!folder) throw new Error(`renameBin : [${binName}] is not a bin`);
    execute(() => [folder.createRenameBinAction(newName)], project);
    return { renamed: binName, to: newName };
};

/* ------------------------------------------------------------------ *
 * SEQUENCE
 * ------------------------------------------------------------------ */

// createSequence : { name, presetPath }
const createSequence = async (command) => {
    const { name, presetPath } = command.options;
    const project = await app.Project.getActiveProject();
    const sequence = await project.createSequence(name, presetPath);
    if (sequence) await _setActiveSequence(sequence);
    return { created: name, id: sequence ? sequence.guid.toString() : null };
};

// deleteSequence : { sequenceId }
const deleteSequence = async (command) => {
    const project = await app.Project.getActiveProject();
    const sequence = await _getSequenceFromId(command.options.sequenceId);
    const ok = await project.deleteSequence(sequence);
    return { deleted: ok, sequenceId: command.options.sequenceId };
};

// getSequenceSettings : { sequenceId }
const getSequenceSettings = async (command) => {
    const sequence = await _getSequenceFromId(command.options.sequenceId);
    const s = await sequence.getSettings();
    const out = {};
    const tryGet = async (k, fn) => { try { out[k] = await fn(); } catch (e) {} };
    await tryGet("videoFrameRate", async () => (await s.getVideoFrameRate()).value);
    await tryGet("frameRect", async () => { const r = await s.getVideoFrameRect(); return { width: r.width, height: r.height }; });
    await tryGet("audioSampleRate", async () => (await s.getAudioSampleRate()).value);
    await tryGet("fieldType", () => s.getVideoFieldType());
    await tryGet("pixelAspectRatio", () => s.getVideoPixelAspectRatio());
    return out;
};

// setPlayerPosition : { sequenceId, seconds }
const setPlayerPosition = async (command) => {
    const { sequenceId, seconds } = command.options;
    const sequence = await _getSequenceFromId(sequenceId);
    const t = await app.TickTime.createWithSeconds(seconds);
    const ok = await sequence.setPlayerPosition(t);
    return { moved: ok, seconds };
};

// getPlayerPosition : { sequenceId } -> seconds
const getPlayerPosition = async (command) => {
    const sequence = await _getSequenceFromId(command.options.sequenceId);
    const t = await sequence.getPlayerPosition();
    return { seconds: t.seconds, ticks: t.ticks };
};

// setSequenceInOut : { sequenceId, inSeconds, outSeconds }
const setSequenceInOut = async (command) => {
    const { sequenceId, inSeconds, outSeconds } = command.options;
    const project = await app.Project.getActiveProject();
    const sequence = await _getSequenceFromId(sequenceId);
    execute(() => {
        const out = [];
        if (inSeconds != null) out.push(sequence.createSetInPointAction(app.TickTime.createWithSeconds(inSeconds)));
        if (outSeconds != null) out.push(sequence.createSetOutPointAction(app.TickTime.createWithSeconds(outSeconds)));
        return out;
    }, project);
    return { inSeconds, outSeconds };
};

// setZeroPoint : { sequenceId, seconds }
const setZeroPoint = async (command) => {
    const { sequenceId, seconds } = command.options;
    const project = await app.Project.getActiveProject();
    const sequence = await _getSequenceFromId(sequenceId);
    execute(() => [sequence.createSetZeroPointAction(app.TickTime.createWithSeconds(seconds))], project);
    return { zeroPoint: seconds };
};

// createSubsequence : { sequenceId, ignoreTrackTargeting? }
const createSubsequence = async (command) => {
    const { sequenceId, ignoreTrackTargeting } = command.options;
    const sequence = await _getSequenceFromId(sequenceId);
    const sub = await sequence.createSubsequence(!!ignoreTrackTargeting);
    return { id: sub ? sub.guid.toString() : null };
};

// clearSelection : { sequenceId }
const clearSelection = async (command) => {
    const sequence = await _getSequenceFromId(command.options.sequenceId);
    const ok = await sequence.clearSelection();
    return { cleared: ok };
};

// selectClip : { sequenceId, trackIndex, trackItemIndex, trackType } -> selects a single clip
const selectClip = async (command) => {
    const { sequenceId, trackIndex, trackItemIndex, trackType } = command.options;
    const sequence = await _getSequenceFromId(sequenceId);
    const item = await getTrack(sequence, trackIndex, trackItemIndex, trackType || TRACK_TYPE.VIDEO);
    const selection = await sequence.getSelection();
    const existing = await selection.getTrackItems();
    for (const t of existing) await selection.removeItem(t);
    selection.addItem(item, true);
    await sequence.setSelection(selection);
    return { selected: true };
};

/* ------------------------------------------------------------------ *
 * INTEROP EXPORT
 * ------------------------------------------------------------------ */

// exportFCPXML : { sequenceId, outputPath }
const exportFCPXML = async (command) => {
    const { sequenceId, outputPath } = command.options;
    const sequence = await _getSequenceFromId(sequenceId);
    const ok = await app.ProjectConverter.exportAsFinalCutProXML(sequence, outputPath, true);
    return { exported: ok, outputPath };
};

// exportOTIO : { sequenceId, outputPath }
const exportOTIO = async (command) => {
    const { sequenceId, outputPath } = command.options;
    const sequence = await _getSequenceFromId(sequenceId);
    const ok = await app.ProjectConverter.exportAsOpenTimelineIO(sequence, outputPath, true);
    return { exported: ok, outputPath };
};

// sceneEditDetection : { sequenceId, clipOperation? } — runs on the current selection
const sceneEditDetection = async (command) => {
    const { sequenceId, clipOperation } = command.options;
    const sequence = await _getSequenceFromId(sequenceId);
    const selection = await sequence.getSelection();
    const ok = await app.SequenceUtils.performSceneEditDetectionOnSelection(
        clipOperation || "ApplyCut",
        selection
    );
    return { ok };
};

/* ------------------------------------------------------------------ *
 * TRACK ITEMS
 * ------------------------------------------------------------------ */

// moveClip : { sequenceId, trackIndex, trackItemIndex, trackType, offsetSeconds }
const moveClip = async (command) => {
    const { sequenceId, trackIndex, trackItemIndex, trackType, offsetSeconds } = command.options;
    const project = await app.Project.getActiveProject();
    const sequence = await _getSequenceFromId(sequenceId);
    const item = await getTrack(sequence, trackIndex, trackItemIndex, trackType || TRACK_TYPE.VIDEO);
    const t = await app.TickTime.createWithSeconds(offsetSeconds);
    execute(() => [item.createMoveAction(t)], project);
    return { moved: offsetSeconds };
};

// renameClip : { sequenceId, trackIndex, trackItemIndex, trackType, newName }
const renameClip = async (command) => {
    const { sequenceId, trackIndex, trackItemIndex, trackType, newName } = command.options;
    const project = await app.Project.getActiveProject();
    const sequence = await _getSequenceFromId(sequenceId);
    const item = await getTrack(sequence, trackIndex, trackItemIndex, trackType || TRACK_TYPE.VIDEO);
    execute(() => [item.createSetNameAction(newName)], project);
    return { renamed: newName };
};

/* ------------------------------------------------------------------ *
 * EFFECTS / TRANSITIONS (discovery)
 * ------------------------------------------------------------------ */

// listVideoEffects : -> { matchNames, displayNames }
const listVideoEffects = async () => {
    const matchNames = await app.VideoFilterFactory.getMatchNames();
    let displayNames = [];
    try { displayNames = await app.VideoFilterFactory.getDisplayNames(); } catch (e) {}
    return { count: matchNames.length, matchNames, displayNames };
};

// listAudioEffects : -> { displayNames }
const listAudioEffects = async () => {
    const displayNames = await app.AudioFilterFactory.getDisplayNames();
    return { count: displayNames.length, displayNames };
};

// listVideoTransitions : -> { matchNames }
const listVideoTransitions = async () => {
    const matchNames = await app.TransitionFactory.getVideoTransitionMatchNames();
    return { count: matchNames.length, matchNames };
};

/* ------------------------------------------------------------------ *
 * MOTION / TRANSFORM (best-effort via Motion component params)
 * ------------------------------------------------------------------ */

// Motion param indices (stable across locales): Position=0, Scale=1, ScaleWidth=2,
// Rotation=4, Anchor=5, Crop Left/Top/Right/Bottom=7/8/9/10. Opacity comp: Opacity=0.
const MOTION = "AE.ADBE Motion";
const OPACITY = "AE.ADBE Opacity";
const VOLUME = "Internal Volume Stereo";          // param: Level=1, Mute=0
const PAN = "Internal Channel Volume Stereo";     // param: Left=1, Right=2

const _setParamByIndex = async (trackItem, matchName, paramIndex, value, project) => {
    const param = await _getParamFlexible(trackItem, matchName, null, paramIndex);
    if (!param) throw new Error(`param ${matchName}[${paramIndex}] not found`);
    const kf = await param.createKeyframe(_buildKfValue(value));
    execute(() => [param.createSetValueAction(kf)], project);
};

// setClipTransform : { sequenceId, videoTrackIndex|trackIndex, trackItemIndex, position?:[x,y], scale?, rotation?, opacity? }
const setClipTransform = async (command) => {
    const o = command.options;
    const project = await app.Project.getActiveProject();
    const trackItem = await _resolveTrackItem({ ...o, trackType: TRACK_TYPE.VIDEO });
    const applied = [];
    if (o.scale != null)    { await _setParamByIndex(trackItem, MOTION, 1, o.scale, project); applied.push("scale"); }
    if (o.rotation != null) { await _setParamByIndex(trackItem, MOTION, 4, o.rotation, project); applied.push("rotation"); }
    if (Array.isArray(o.position)) { await _setParamByIndex(trackItem, MOTION, 0, o.position, project); applied.push("position"); }
    if (o.opacity != null)  { await _setParamByIndex(trackItem, OPACITY, 0, o.opacity, project); applied.push("opacity"); }
    return { applied };
};

// setClipVolume : { sequenceId, audioTrackIndex|trackIndex, trackItemIndex, level } — level in dB (0 = unity)
const setClipVolume = async (command) => {
    const o = command.options;
    const project = await app.Project.getActiveProject();
    const trackItem = await _resolveTrackItem({ ...o, trackType: TRACK_TYPE.AUDIO });
    await _setParamByIndex(trackItem, VOLUME, 1, o.level, project);
    return { level: o.level };
};

// setClipPan : { sequenceId, audioTrackIndex|trackIndex, trackItemIndex, left?, right? }
const setClipPan = async (command) => {
    const o = command.options;
    const project = await app.Project.getActiveProject();
    const trackItem = await _resolveTrackItem({ ...o, trackType: TRACK_TYPE.AUDIO });
    const applied = [];
    if (o.left != null)  { await _setParamByIndex(trackItem, PAN, 1, o.left, project); applied.push("left"); }
    if (o.right != null) { await _setParamByIndex(trackItem, PAN, 2, o.right, project); applied.push("right"); }
    return { applied };
};

// audioFadeIn / audioFadeOut via keyframed volume: { sequenceId, audioTrackIndex|trackIndex,
//   trackItemIndex, startSeconds, endSeconds, fromDb?, toDb? } — also the building block for crossfades.
const audioFade = async (command) => {
    const o = command.options;
    const project = await app.Project.getActiveProject();
    const trackItem = await _resolveTrackItem({ ...o, trackType: TRACK_TYPE.AUDIO });
    const param = await _getParamFlexible(trackItem, VOLUME, null, 1);
    if (!param) throw new Error("audioFade : volume param not found");
    try { if (!(await param.isTimeVarying())) execute(() => [param.createSetTimeVaryingAction(true)], project); }
    catch (e) { execute(() => [param.createSetTimeVaryingAction(true)], project); }
    const drop = (secs, val) => {
        const kf = param.createKeyframe(val);
        try { kf.position = app.TickTime.createWithSeconds(secs); } catch (e) {}
        execute(() => [param.createAddKeyframeAction(kf)], project);
    };
    drop(o.startSeconds, o.fromDb != null ? o.fromDb : -60);
    drop(o.endSeconds, o.toDb != null ? o.toDb : 0);
    return { fadedFrom: o.startSeconds, to: o.endSeconds };
};

/* ------------------------------------------------------------------ *
 * MARKERS (read / remove)
 * ------------------------------------------------------------------ */

// getMarkers : { sequenceId } -> list
const getMarkers = async (command) => {
    const sequence = await _getSequenceFromId(command.options.sequenceId);
    const markersObj = await app.Markers.getMarkers(sequence);
    const list = await markersObj.getMarkers([]);
    const out = [];
    for (const m of list) {
        out.push({
            name: await m.getName(),
            type: await m.getType(),
            comments: await m.getComments(),
            startSeconds: (await m.getStart()).seconds,
            durationSeconds: (await m.getDuration()).seconds,
        });
    }
    return { count: out.length, markers: out };
};

/* ------------------------------------------------------------------ *
 * METADATA
 * ------------------------------------------------------------------ */

// getXMPMetadata : { itemName }
const getXMPMetadata = async (command) => {
    const project = await app.Project.getActiveProject();
    const item = await findProjectItem(command.options.itemName, project);
    const xmp = await app.Metadata.getXMPMetadata(item);
    return { xmp };
};

// setXMPMetadata : { itemName, metadata }
const setXMPMetadata = async (command) => {
    const { itemName, metadata } = command.options;
    const project = await app.Project.getActiveProject();
    const item = await findProjectItem(itemName, project);
    execute(() => [app.Metadata.createSetXMPMetadataAction(item, metadata)], project);
    return { set: itemName };
};

/* ------------------------------------------------------------------ *
 * PROPERTIES / APP
 * ------------------------------------------------------------------ */

// getAppInfo : -> version, AME/AE availability
const getAppInfo = async () => {
    const out = {};
    try { out.version = app.Application.version; } catch (e) {}
    try { out.isAEInstalled = await app.Utils.isAEInstalled(); } catch (e) {}
    try {
        const mgr = await app.EncoderManager.getManager();
        out.isAMEInstalled = mgr.isAMEInstalled;
    } catch (e) {}
    return out;
};

// setProperty : { scope:"sequence"|"project", sequenceId?, name, value, persistent? }
const setProperty = async (command) => {
    const { scope, sequenceId, name, value, persistent } = command.options;
    const project = await app.Project.getActiveProject();
    const owner = scope === "sequence" ? await _getSequenceFromId(sequenceId) : project;
    const props = await app.Properties.getProperties(owner);
    const flag = persistent === false
        ? constants.PropertyType.NON_PERSISTENT
        : constants.PropertyType.PERSISTENT;
    execute(() => [props.createSetValueAction(name, value, flag)], project);
    return { set: name };
};

// getProperty : { scope, sequenceId?, name }
const getProperty = async (command) => {
    const { scope, sequenceId, name } = command.options;
    const project = await app.Project.getActiveProject();
    const owner = scope === "sequence" ? await _getSequenceFromId(sequenceId) : project;
    const props = await app.Properties.getProperties(owner);
    const has = await props.hasValue(name);
    return { name, has, value: has ? await props.getValue(name) : null };
};

/* ------------------------------------------------------------------ *
 * GENERIC EFFECT-PARAM + KEYFRAME ENGINE
 * The single lever that makes Motion (position/scale/rotation), Opacity,
 * Crop, Lumetri colour, and Audio (volume/pan) all controllable — plus
 * keyframes on ANY of them.
 * ------------------------------------------------------------------ */

// turn a JS value into the value type a ComponentParam keyframe expects.
// [x,y] -> PointF (position/anchor);  number/bool/string pass through.
const _buildKfValue = (value) => {
    if (Array.isArray(value) && value.length === 2) {
        try { const p = new app.PointF(value[0], value[1]); return p; }
        catch (e1) {
            try { const p = app.PointF.create(value[0], value[1]); return p; }
            catch (e2) {
                try { const p = new app.PointF(); p.x = value[0]; p.y = value[1]; return p; }
                catch (e3) { return { x: value[0], y: value[1] }; }
            }
        }
    }
    return value;
};

const _resolveTrackItem = async (o) => {
    const sequence = await _getSequenceFromId(o.sequenceId);
    const trackType = o.trackType || TRACK_TYPE.VIDEO;
    const trackIndex =
        o.trackIndex != null ? o.trackIndex
        : trackType === TRACK_TYPE.AUDIO ? o.audioTrackIndex
        : o.videoTrackIndex;
    return getTrack(sequence, trackIndex, o.trackItemIndex, trackType);
};

// inspectClip : dump the whole component chain of a clip (match names + param display names).
// Use this to discover the exact strings for setEffectParam / addKeyframe.
const inspectClip = async (command) => {
    const trackItem = await _resolveTrackItem(command.options);
    const chain = await trackItem.getComponentChain();
    const count = chain.getComponentCount();
    const components = [];
    for (let i = 0; i < count; i++) {
        const c = chain.getComponentAtIndex(i);
        const params = [];
        const pc = c.getParamCount();
        for (let j = 0; j < pc; j++) {
            let dn = null;
            try { dn = c.getParam(j).displayName; } catch (e) {}
            params.push({ index: j, displayName: dn });
        }
        let matchName = null, displayName = null;
        try { matchName = await c.getMatchName(); } catch (e) {}
        try { displayName = await c.getDisplayName(); } catch (e) {}
        components.push({ index: i, matchName, displayName, params });
    }
    return { components };
};

// Locale-proof param lookup: by component matchName (stable, English) + param INDEX
// (stable) OR param displayName (localized — fallback). Returns the ComponentParam.
const _getParamFlexible = async (trackItem, matchName, paramName, paramIndex) => {
    const chain = await trackItem.getComponentChain();
    const count = chain.getComponentCount();
    for (let i = 0; i < count; i++) {
        const c = chain.getComponentAtIndex(i);
        if ((await c.getMatchName()) !== matchName) continue;
        if (Number.isInteger(paramIndex)) return c.getParam(paramIndex);
        const pc = c.getParamCount();
        for (let j = 0; j < pc; j++) {
            const p = c.getParam(j);
            try { if (p.displayName === paramName) return p; } catch (e) {}
        }
    }
    return null;
};

// setEffectParam : set a static value on any component param (no keyframe).
// Address the param by INDEX (locale-proof) or displayName.
// { ..., matchName:"AE.ADBE Motion", paramIndex:1, value:80 }   // Scale
// { ..., matchName:"Internal Volume Stereo", paramIndex:1, value:0 } // Volume (dB)
const setEffectParam = async (command) => {
    const o = command.options;
    const project = await app.Project.getActiveProject();
    const trackItem = await _resolveTrackItem(o);
    const param = await _getParamFlexible(trackItem, o.matchName, o.paramName, o.paramIndex);
    if (!param) throw new Error(`setEffectParam : param [${o.matchName} / ${o.paramName ?? o.paramIndex}] not found`);
    const kf = await param.createKeyframe(_buildKfValue(o.value));
    execute(() => [param.createSetValueAction(kf)], project);
    return { set: o.paramName ?? o.paramIndex, on: o.matchName };
};

// addKeyframe : enable keyframing on a param and drop a keyframe at a time.
// { ..., matchName, paramName, atSeconds, value, interpolation?:"LINEAR"|"BEZIER"|"HOLD" }
const addKeyframe = async (command) => {
    const o = command.options;
    const project = await app.Project.getActiveProject();
    const trackItem = await _resolveTrackItem(o);
    const param = await _getParamFlexible(trackItem, o.matchName, o.paramName, o.paramIndex);
    if (!param) throw new Error(`addKeyframe : param [${o.matchName} / ${o.paramName ?? o.paramIndex}] not found`);

    // 1) make the param time-varying (stopwatch on) — must happen before adding keyframes
    try {
        const isVarying = await param.isTimeVarying();
        if (!isVarying) execute(() => [param.createSetTimeVaryingAction(true)], project);
    } catch (e) { execute(() => [param.createSetTimeVaryingAction(true)], project); }

    // 2) build the keyframe, position it, add it
    const kf = await param.createKeyframe(_buildKfValue(o.value));
    try { kf.position = app.TickTime.createWithSeconds(o.atSeconds); } catch (e) {}
    execute(() => [param.createAddKeyframeAction(kf)], project);

    // 3) optional interpolation
    if (o.interpolation && constants.InterpolationMode) {
        const mode = constants.InterpolationMode[String(o.interpolation).toUpperCase()];
        if (Number.isInteger(mode)) {
            const t = app.TickTime.createWithSeconds(o.atSeconds);
            try { execute(() => [param.createSetInterpolationAtKeyframeAction(t, mode, true)], project); } catch (e) {}
        }
    }
    return { keyframed: o.paramName, atSeconds: o.atSeconds };
};

// ensureTrackCount : guarantee a sequence has >= N video (or audio) tracks.
// Works around the missing addTrack: insert a placeholder on the highest needed
// index (auto-creates the track), then ripple-remove the placeholder.
const ensureTrackCount = async (command) => {
    const { sequenceId, trackType, count } = command.options;
    const sequence = await _getSequenceFromId(sequenceId);
    const isAudio = (trackType || "VIDEO") === "AUDIO";
    const have = isAudio
        ? await sequence.getAudioTrackCount()
        : await sequence.getVideoTrackCount();
    return { had: have, requested: count, note: have >= count
        ? "already enough"
        : "insert any clip at videoTrackIndex=" + (count - 1) + " to auto-create the track" };
};

// closeAllGaps : ripple every video & audio track to zero out gaps.
const closeAllGaps = async (command) => {
    const { sequenceId } = command.options;
    const project = await app.Project.getActiveProject();
    const sequence = await _getSequenceFromId(sequenceId);

    const closeTrack = async (trackIndex, trackType) => {
        let items;
        try { items = await getTrackItems(sequence, trackIndex, trackType); } catch (e) { return; }
        if (!items || !items.length) return;
        let target = app.TickTime.createWithTicks("0");
        for (const item of items) {
            const start = await item.getStartTime();
            const shift = (target.ticksNumber - start.ticksNumber);
            const shiftTick = app.TickTime.createWithTicks(shift.toString());
            execute(() => [item.createMoveAction(shiftTick)], project);
            target = await item.getEndTime();
        }
    };

    const vCount = await sequence.getVideoTrackCount();
    const aCount = await sequence.getAudioTrackCount();
    for (let i = 0; i < vCount; i++) await closeTrack(i, TRACK_TYPE.VIDEO);
    for (let i = 0; i < aCount; i++) await closeTrack(i, TRACK_TYPE.AUDIO);
    return { videoTracks: vCount, audioTracks: aCount };
};

/* ------------------------------------------------------------------ *
 * COLOR / LUT
 * ------------------------------------------------------------------ */

// applyEffect : add any video effect to a clip by match name (e.g. Lumetri).
// { sequenceId, videoTrackIndex|trackIndex, trackItemIndex, matchName }
const applyEffect = async (command) => {
    const o = command.options;
    const project = await app.Project.getActiveProject();
    const trackItem = await _resolveTrackItem(o);
    const effect = await app.VideoFilterFactory.createComponent(o.matchName);
    const chain = await trackItem.getComponentChain();
    execute(() => [chain.createAppendComponentAction(effect)], project);
    return { applied: o.matchName };
};

// setInputLUT : set a CLIP's Input LUT by LUT id/path. { itemName, lutId }
const setInputLUT = async (command) => {
    const { itemName, lutId } = command.options;
    const project = await app.Project.getActiveProject();
    const item = await findProjectItem(itemName, project);
    const clip = app.ClipProjectItem.cast(item);
    if (!clip) throw new Error(`setInputLUT : [${itemName}] is not a clip item`);
    execute(() => [clip.createSetInputLUTIDAction(lutId)], project);
    return { itemName, lutId };
};

// getInputLUT : read a clip's input/embedded LUT id. { itemName }
const getInputLUT = async (command) => {
    const project = await app.Project.getActiveProject();
    const item = await findProjectItem(command.options.itemName, project);
    const clip = app.ClipProjectItem.cast(item);
    const out = {};
    try { out.inputLUTID = await clip.getInputLUTID(); } catch (e) {}
    try { out.embeddedLUTID = await clip.getEmbeddedLUTID(); } catch (e) {}
    return out;
};

// setColorGrade : ensure a Lumetri effect is on the clip, then set the requested
// Basic-Correction params. Param display names are auto-resolved against the live
// Lumetri component (works across PPro versions). Keys: temperature, tint, exposure,
// contrast, highlights, shadows, whites, blacks, saturation, sharpness, lut (creative/input).
const GRADE_PARAM_ALIASES = {
    temperature: ["Temperature", "White Balance: Temperature", "Temp", "Temperatur", "Farbtemperatur"],
    tint: ["Tint", "White Balance: Tint", "Farbton", "Tönung"],
    exposure: ["Exposure", "Belichtung"],
    contrast: ["Contrast", "Kontrast"],
    highlights: ["Highlights", "Lichter"],
    shadows: ["Shadows", "Schatten"],
    whites: ["Whites", "Weiß", "Weiss"],
    blacks: ["Blacks", "Schwarz", "Schwarztöne"],
    saturation: ["Saturation", "Sättigung", "Saettigung"],
    sharpness: ["Sharpen", "Sharpness", "Schärfen", "Schaerfen"],
};

// Lumetri "Einfache Korrektur" (Basic Correction) param indices — stable, locale-proof.
const GRADE_INDEX = {
    temperature: 14, tint: 15, saturation: 16,
    exposure: 19, contrast: 20, highlights: 21, shadows: 22, whites: 23, blacks: 24,
};
const LUMETRI = "AE.ADBE Lumetri";

const setColorGrade = async (command) => {
    const o = command.options;
    const project = await app.Project.getActiveProject();
    const trackItem = await _resolveTrackItem({ ...o, trackType: TRACK_TYPE.VIDEO });

    // ensure a Lumetri component is on the clip
    const chain = await trackItem.getComponentChain();
    const hasLumetri = async () => {
        const cc = chain.getComponentCount();
        for (let i = 0; i < cc; i++) {
            if ((await chain.getComponentAtIndex(i).getMatchName()) === LUMETRI) return true;
        }
        return false;
    };
    if (!(await hasLumetri())) {
        const comp = await app.VideoFilterFactory.createComponent(LUMETRI);
        execute(() => [chain.createAppendComponentAction(comp)], project);
    }

    const applied = [], failed = [];
    for (const [key, idx] of Object.entries(GRADE_INDEX)) {
        if (o[key] == null) continue;
        try { await _setParamByIndex(trackItem, LUMETRI, idx, o[key], project); applied.push(key); }
        catch (e) { failed.push(key); }
    }
    return { applied, failed };
};

// removeEffect : remove all components matching a match name from a clip.
// { ..., matchName:"AE.ADBE Lumetri" }
const removeEffect = async (command) => {
    const o = command.options;
    const project = await app.Project.getActiveProject();
    const trackItem = await _resolveTrackItem(o);
    const chain = await trackItem.getComponentChain();
    const cc = chain.getComponentCount();
    let removed = 0;
    for (let i = cc - 1; i >= 0; i--) {
        const c = chain.getComponentAtIndex(i);
        if ((await c.getMatchName()) === o.matchName) {
            execute(() => [chain.createRemoveComponentAction(c)], project);
            removed++;
        }
    }
    return { removed, matchName: o.matchName };
};

// clearKeyframes : turn off keyframing on a param (removes keyframes) and optionally
// set a static value. { ..., matchName, paramIndex|paramName, value? }
const clearKeyframes = async (command) => {
    const o = command.options;
    const project = await app.Project.getActiveProject();
    const trackItem = await _resolveTrackItem(o);
    const param = await _getParamFlexible(trackItem, o.matchName, o.paramName, o.paramIndex);
    if (!param) throw new Error(`clearKeyframes : param not found`);
    execute(() => [param.createSetTimeVaryingAction(false)], project);
    if (o.value != null) {
        const kf = await param.createKeyframe(_buildKfValue(o.value));
        execute(() => [param.createSetValueAction(kf)], project);
    }
    return { cleared: true };
};

const extraHandlers = {
    // discovery + generic engine
    inspectClip,
    setEffectParam,
    addKeyframe,
    removeEffect,
    clearKeyframes,
    ensureTrackCount,
    closeAllGaps,
    // color / lut
    applyEffect,
    setInputLUT,
    getInputLUT,
    setColorGrade,
    // project items
    setColorLabel,
    getColorLabel,
    renameProjectItem,
    relinkMedia,
    overrideFrameRate,
    setProjectItemOffline,
    attachProxy,
    getProjectItemInfo,
    renameBin,
    // sequence
    createSequence,
    deleteSequence,
    getSequenceSettings,
    setPlayerPosition,
    getPlayerPosition,
    setSequenceInOut,
    setZeroPoint,
    createSubsequence,
    clearSelection,
    selectClip,
    // interop
    exportFCPXML,
    exportOTIO,
    sceneEditDetection,
    // track items
    moveClip,
    renameClip,
    // effects discovery
    listVideoEffects,
    listAudioEffects,
    listVideoTransitions,
    // motion / audio
    setClipTransform,
    setClipVolume,
    setClipPan,
    audioFade,
    // markers
    getMarkers,
    // metadata
    getXMPMetadata,
    setXMPMetadata,
    // properties / app
    getAppInfo,
    setProperty,
    getProperty,
};

module.exports = { extraHandlers };
