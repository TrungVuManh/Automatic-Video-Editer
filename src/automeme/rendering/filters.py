r"""Dựng filter_complex cho FFmpeg — hàm thuần, không gọi FFmpeg (SPEC §40).

Mỗi meme/SFX là một input riêng (`-i`), nên đường dẫn **không bao giờ** nằm trong chuỗi filter —
tránh hẳn chuyện escape `:` và `\` trên Windows.

**Meme ở góc** (`mode="overlay"`, SPEC §36–38):

    [1:v]scale=w=576:h=486:force_original_aspect_ratio=decrease:force_divisible_by=2,…[m0]
    [0:v][m0]overlay=W-w-58:H-h-58:enable='between(t,8.880,10.230)':eof_action=pass[v]

- `scale`: rộng tối đa = `scale` × bề rộng video, cao tối đa = `max_height_ratio` × chiều cao;
  giữ tỉ lệ ảnh, cạnh luôn chẵn.
- `setpts`: dời meme tới đúng thời điểm, để GIF bắt đầu chạy từ khung đầu.
- `enable`: chỉ hiện trong khoảng của sự kiện; `eof_action=pass` để video chính không bị cắt.

**Meme tràn màn hình** (`mode="cutaway"`, SPEC §36) — kiểu dựng của kênh game chuyên nghiệp:
nền là chính meme phóng lấp khung rồi làm mờ + tối (không có viền đen), meme đặt giữa vừa khung,
vào khung ở 106% rồi thu về 100% (`zoompan`), mờ dần vào/ra rất nhanh. Video gốc vẫn chạy bên
dưới nên độ dài và mọi mốc thời gian phía sau không đổi.

**Zoom** (`ZoomEvent`, SPEC §72): phóng khung hình gốc tới `factor` bằng `zoompan` theo số khung
hình — chỉ thêm filter này khi timeline có zoom, vì nó xử lý lại mọi khung hình.

**Âm thanh**: SFX được `adelay` tới đúng lúc rồi `amix` với tiếng gốc; trong lúc cắt tràn màn
hình tiếng gốc được hạ xuống có dốc lên/xuống; cuối cùng `alimiter` chặn đỉnh để không vỡ tiếng.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from ..timeline.schema import MemeEvent, SfxEvent, TimelineEvent, ZoomEvent

# Đuôi file được coi là ảnh động (phải cho lặp) và ảnh tĩnh (phải giữ một khung hình)
DUOI_ANH_DONG = {".gif", ".webp", ".apng"}
DUOI_VIDEO = {".mp4", ".mov", ".mkv", ".webm"}
FPS_MAC_DINH = 30.0  # khi ffprobe không đọc được fps của video nguồn


@dataclass(frozen=True)
class CutawayStyle:
    """Nhịp và hình thức của cú cắt tràn màn hình (lấy từ `configs/`, mục `cutaway`)."""

    inset: float = 0.92          # meme chiếm tối đa 92% khung, chừa viền nền mờ
    blur: int = 24               # độ mờ của nền (chính meme phóng lấp khung)
    darken: float = -0.18        # làm tối nền để meme nổi lên
    settle_zoom: float = 1.06    # vào khung ở 106%…
    settle_time: float = 0.15    # …rồi thu về 100% trong chừng này giây
    fade_in: float = 0.06
    fade_out: float = 0.08
    duck_volume: float = 0.35    # tiếng gốc còn 35% trong lúc cắt
    duck_ramp: float = 0.08      # dốc hạ/trả tiếng, tránh tắt-bật đột ngột
    zoom_ease: float = 0.12      # thời gian zoom tới mức đích
    limiter: float = 0.891       # trần đỉnh âm (≈ −1 dBFS)


def cutaway_style(cfg) -> CutawayStyle:
    """`settings.cutaway` → CutawayStyle (chỉ lấy các khóa về hình thức và âm thanh)."""
    return CutawayStyle(
        inset=cfg.inset, blur=cfg.blur, darken=cfg.darken, settle_zoom=cfg.settle_zoom,
        settle_time=cfg.settle_time, fade_in=cfg.fade_in, fade_out=cfg.fade_out,
        duck_volume=cfg.duck_volume, duck_ramp=cfg.duck_ramp, limiter=cfg.limiter,
    )


STYLE_MAC_DINH = CutawayStyle()


@dataclass(frozen=True)
class RenderPlan:
    input_args: list[str]   # tham số -i của các meme/SFX, theo đúng thứ tự sự kiện có asset
    filter_complex: str     # rỗng nếu không có gì cần lọc
    out_label: str          # nhãn luồng video ra, ví dụ "[v]"; rỗng khi không lọc hình
    out_audio_label: str = ""  # nhãn audio đã xử lý; rỗng thì dùng audio gốc


def build_render_plan(events: Sequence[TimelineEvent], asset_paths: Sequence[Path | None], *,
                      video_w: int, video_h: int, scale_default: float,
                      position_default: str, margin_ratio: float,
                      max_height_ratio: float = 1.0, has_audio: bool = True,
                      fps: float | None = None,
                      style: CutawayStyle = STYLE_MAC_DINH) -> RenderPlan:
    """Sự kiện + asset (None với zoom) → input, chuỗi lọc hình và chuỗi xử lý âm thanh."""
    if len(events) != len(asset_paths):
        raise ValueError("Số sự kiện và số đường dẫn asset không khớp")
    if not events:
        return RenderPlan(input_args=[], filter_complex="", out_label="")

    fps_v = fps or FPS_MAC_DINH
    le = max(0, round(video_w * margin_ratio))
    input_args: list[str] = []
    chuan_bi_video: list[str] = []
    chuan_bi_audio: list[str] = []
    chuoi_overlay: list[str] = []
    meme_rows: list[tuple[int, MemeEvent]] = []
    zooms = [e for e in events if isinstance(e, ZoomEvent)]
    sfx_labels: list[str] = []

    input_index = 0
    for e, asset in zip(events, asset_paths, strict=True):
        if isinstance(e, ZoomEvent):
            continue  # zoom biến đổi khung hình gốc, không có input riêng
        if asset is None:
            raise ValueError(f"Sự kiện {e.id} thiếu đường dẫn asset")
        input_index += 1
        if isinstance(e, SfxEvent):
            input_args += ["-i", str(asset)]
            label = f"[s{len(sfx_labels)}]"
            delay_ms = max(0, round(e.start * 1000))
            chuan_bi_audio.append(
                f"[{input_index}:a]atrim=0:{e.duration:.3f},asetpts=PTS-STARTPTS,"
                f"volume={e.volume:.3f},adelay={delay_ms}|{delay_ms}{label}"
            )
            sfx_labels.append(label)
            continue
        input_args += input_cho_meme(asset, e.duration)
        meme_rows.append((input_index, e))

    nhan_truoc = "[0:v]"
    if zooms:
        nhan_zoom = "[v]" if not meme_rows else "[vz]"
        chuan_bi_video.append(
            f"[0:v]zoompan=z='{zoom_expr(zooms, fps_v, style.zoom_ease)}':"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:"
            f"s={_chan(video_w)}x{_chan(video_h)}:fps={_fps(fps_v)},setsar=1{nhan_zoom}"
        )
        nhan_truoc = nhan_zoom

    for i, (idx, e) in enumerate(meme_rows):
        if e.mode == "cutaway":
            chuan_bi_video.append(cutaway_chain(idx, i, e, video_w, video_h, fps_v, style))
            x, y = "0", "0"
        else:
            rong = _chan(video_w * (e.scale if e.scale is not None else scale_default))
            cao = _chan(video_h * max_height_ratio)
            chuan_bi_video.append(
                f"[{idx}:v]scale=w={rong}:h={cao}:force_original_aspect_ratio=decrease:"
                f"force_divisible_by=2,setpts=PTS-STARTPTS+{e.start:.3f}/TB[m{i}]"
            )
            x, y = vi_tri_overlay(e.position or position_default, le)
        nhan_sau = "[v]" if i == len(meme_rows) - 1 else f"[v{i}]"
        chuoi_overlay.append(
            f"{nhan_truoc}[m{i}]overlay={x}:{y}:"
            f"enable='between(t,{e.start:.3f},{e.end:.3f})':eof_action=pass{nhan_sau}"
        )
        nhan_truoc = nhan_sau

    out_audio = _audio_chain(chuan_bi_audio, sfx_labels, meme_rows, has_audio, style)
    filters = chuan_bi_video + chuoi_overlay + chuan_bi_audio
    return RenderPlan(
        input_args=input_args,
        filter_complex=";".join(filters),
        out_label="[v]" if (meme_rows or zooms) else "",
        out_audio_label=out_audio,
    )


def cutaway_chain(idx: int, i: int, e: MemeEvent, video_w: int, video_h: int, fps: float,
                  style: CutawayStyle) -> str:
    """Input meme → khung tràn màn hình [m<i>] cùng cỡ video, đã dời tới `e.start`."""
    w, h = _chan(video_w), _chan(video_h)
    wi, hi = _chan(video_w * style.inset), _chan(video_h * style.inset)
    so_khung = max(1, round(style.settle_time * fps))
    z = style.settle_zoom
    fade_out_at = max(0.0, e.duration - style.fade_out)
    return ";".join([
        f"[{idx}:v]fps={_fps(fps)},split=2[cb{i}][cf{i}]",
        f"[cb{i}]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},"
        f"boxblur={style.blur}:2,eq=brightness={style.darken:.2f},setsar=1[cbb{i}]",
        f"[cf{i}]scale=w={wi}:h={hi}:force_original_aspect_ratio=decrease:"
        f"force_divisible_by=2,setsar=1[cff{i}]",
        f"[cbb{i}][cff{i}]overlay=(W-w)/2:(H-h)/2:shortest=1,"
        f"zoompan=z='max(1,{z:.3f}-{z - 1:.3f}*on/{so_khung})':"
        f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={w}x{h}:fps={_fps(fps)},"
        f"format=yuva420p,fade=t=in:st=0:d={style.fade_in:.3f}:alpha=1,"
        f"fade=t=out:st={fade_out_at:.3f}:d={style.fade_out:.3f}:alpha=1,"
        f"setpts=PTS-STARTPTS+{e.start:.3f}/TB[m{i}]",
    ])


def zoom_expr(zooms: Sequence[ZoomEvent], fps: float, ease: float) -> str:
    """Hệ số zoom theo khung hình (`on`): tăng dần tới `factor`, giữ, rồi trả nhanh về 1.

    Mỗi zoom là 1 + (factor−1)·clip((t−s)/ease,0,1)·clip((e−t)/ease_ra,0,1) — ngoài khoảng
    [s, e] một trong hai `clip` bằng 0 nên hệ số tự về 1. Nhiều zoom thì lấy `max`.
    """
    t = f"on/{_fps(fps)}"
    ease_ra = max(0.02, ease / 2)
    parts = [
        f"1+{z.factor - 1:.3f}*clip(({t}-{z.start:.3f})/{ease:.3f},0,1)"
        f"*clip(({z.end:.3f}-{t})/{ease_ra:.3f},0,1)"
        for z in zooms
    ]
    expr = parts[0]
    for part in parts[1:]:
        expr = f"max({expr},{part})"
    return expr


def duck_expr(cutaways: Sequence[MemeEvent], volume: float, ramp: float) -> str:
    """Hệ số âm lượng tiếng gốc theo thời gian `t`: hạ còn `volume` trong lúc cắt, có dốc."""
    parts = [
        f"1-{1 - volume:.3f}*clip((t-{e.start - ramp:.3f})/{ramp:.3f},0,1)"
        f"*clip(({e.end + ramp:.3f}-t)/{ramp:.3f},0,1)"
        for e in cutaways
    ]
    expr = parts[0]
    for part in parts[1:]:
        expr = f"min({expr},{part})"
    return expr


def _audio_chain(chuan_bi_audio: list[str], sfx_labels: list[str],
                 meme_rows: list[tuple[int, MemeEvent]], has_audio: bool,
                 style: CutawayStyle) -> str:
    """Thêm hạ tiếng + trộn SFX + chặn đỉnh vào `chuan_bi_audio`; trả về nhãn audio ra."""
    cutaways = [e for _, e in meme_rows if e.mode == "cutaway"]
    goc = "[0:a]" if has_audio else ""
    if has_audio and cutaways:
        chuan_bi_audio.append(
            f"[0:a]volume=volume='{duck_expr(cutaways, style.duck_volume, style.duck_ramp)}':"
            f"eval=frame[ad]"
        )
        goc = "[ad]"
    if not sfx_labels and goc in ("", "[0:a]"):
        return ""  # không có gì thay đổi tiếng: copy nguyên audio gốc

    mix_inputs = ([goc] if goc else []) + sfx_labels
    if len(mix_inputs) == 1:
        nguon = mix_inputs[0]
    else:
        chuan_bi_audio.append(
            "".join(mix_inputs)
            + f"amix=inputs={len(mix_inputs)}:duration="
            + ("first" if has_audio else "longest")
            + ":dropout_transition=0:normalize=0[am]"
        )
        nguon = "[am]"
    chuan_bi_audio.append(f"{nguon}alimiter=limit={style.limiter:.3f}:level=0[a]")
    return "[a]"


def input_cho_meme(asset: Path, duration: float) -> list[str]:
    """Tham số `-i` tùy loại meme.

    Ảnh tĩnh phải `-loop 1` (nếu không chỉ có đúng một khung hình), ảnh động phải
    `-ignore_loop 0` để lặp hết thời lượng sự kiện. `-t` cắt input cho khỏi kéo dài vô tận.
    """
    duoi = asset.suffix.lower()
    thoi_luong = f"{duration:.3f}"
    if duoi in DUOI_ANH_DONG:
        return ["-ignore_loop", "0", "-t", thoi_luong, "-i", str(asset)]
    if duoi in DUOI_VIDEO:
        return ["-stream_loop", "-1", "-t", thoi_luong, "-i", str(asset)]
    return ["-loop", "1", "-t", thoi_luong, "-i", str(asset)]


def vi_tri_overlay(position: str, le: int) -> tuple[str, str]:
    """Vị trí → biểu thức x, y cho overlay (SPEC §37).

    Dùng biến W/H (khung nền) và w/h (meme) của FFmpeg nên không cần biết trước cỡ meme.
    """
    bang = {
        "top-left": (f"{le}", f"{le}"),
        "top-right": (f"W-w-{le}", f"{le}"),
        "bottom-left": (f"{le}", f"H-h-{le}"),
        "bottom-right": (f"W-w-{le}", f"H-h-{le}"),
        "center": ("(W-w)/2", "(H-h)/2"),
    }
    if position not in bang:
        raise ValueError(f"Vị trí không hợp lệ: {position!r}")
    return bang[position]


def _fps(fps: float) -> str:
    """fps gọn cho FFmpeg: 60.0 → "60", 29.97 → "29.97"."""
    return f"{fps:.3f}".rstrip("0").rstrip(".")


def _chan(n: float) -> int:
    """Làm tròn xuống số chẵn — libx264 yêu cầu cạnh chẵn."""
    return max(2, int(n // 2) * 2)
