# theme_manager.py
"""
Theme generation utilities to keep overlays visible and accessible.

Generates two modes:
- CLASSIC: green pitch with white lines; offside/arrow chosen distinct from
  grass/line/ball and both team colors
- BLACK & WHITE: grayscale pitch adapted to team brightness; distinct chroma
  hues for offside and arrow to pop out
"""
from typing import Dict
from utils.color_utils import hex_to_lab, delta_e_lab, lch_to_hex, contrast_ratio, hex_to_lch, hex_to_rgb, relative_luminance
from config import BALL_COLOR

# Fallback: [grass, line, offside, arrow]
FALLBACK = ["#08711a", "#E4E4E4", "#FF40FF", "#000000"]
CLASSIC_GRASS = "#08711a"
CLASSIC_LINE = "#E4E4E4"
BW_GRASS_IF_LIGHT = "#292929"
BW_GRASS_IF_DARK = "#E4E4E4"
BW_LINE_IF_LIGHT = "#E4E4E4"
BW_LINE_IF_DARK = "#292929"

def is_light(hexcolor):
    """Return True if a hex color is considered light.

    Parameters
    ----------
    hexcolor : str
        Hex color string like '#RRGGBB'.

    Returns
    -------
    bool
        True if simple luma heuristic > 0.7.
    """
    r, g, b = int(hexcolor[1:3],16), int(hexcolor[3:5],16), int(hexcolor[5:7],16)
    return (0.299*r + 0.587*g + 0.114*b)/255.0 > 0.7

def majority_light(colors):
    """Return True if at least two colors in the list are light.

    Parameters
    ----------
    colors : list[str]
        Hex colors.

    Returns
    -------
    bool
        True if a majority are light by :func:`is_light`.
    """
    lights = sum(is_light(c) for c in colors)
    return lights >= 2  # majority out of 4

class ThemeManager:
    """Produce color themes ensuring contrast and distinct hues.

    Parameters
    ----------
    de_min : float, default 25.0
        Minimum ΔE00 between chosen colors and forbidden references.
    """
    def __init__(self, de_min: float = 25.0):
        self.de_min = de_min
        # Cache computed themes to avoid recomputation when switching
        self._cache: Dict[tuple, Dict[str, str]] = {}

    def fallback(self) -> Dict[str, str]:
        """Return a conservative, always-valid theme as a safety net.

        Returns
        -------
        dict[str, str]
            Keys: 'grass', 'line', 'offside', 'arrow'.
        """
        return {"grass": FALLBACK[0], "line": FALLBACK[1], "offside": FALLBACK[2], "arrow": FALLBACK[3]}

    def generate(self, mode: str, home_hex: str, away_hex: str, home_sec: str, away_sec: str) -> Dict[str, str]:
        """Generate a theme for overlays given team colors and mode.

        Parameters
        ----------
        mode : {'CLASSIC','BLACK & WHITE'}
        home_hex, away_hex : str
            Primary shirt colors for Home and Away.
        home_sec, away_sec : str
            Secondary shirt colors for Home and Away.

        Returns
        -------
        dict[str, str]
            Theme with keys: 'grass', 'line', 'offside', 'arrow'.
        """
        home = "#" + home_hex.lstrip("#")
        away = "#" + away_hex.lstrip("#")
        home_sec = "#" + home_sec.lstrip("#")
        away_sec = "#" + away_sec.lstrip("#")
        all_teams = [home, away, home_sec, away_sec]
        ball = BALL_COLOR
        mode_upper = mode.upper()

        # Cache key per mode and team colors
        cache_key = (mode_upper, home, away, home_sec, away_sec)
        if cache_key in self._cache:
            return self._cache[cache_key]

        # === CLASSIC ===
        if mode_upper == "CLASSIC":
            grass = CLASSIC_GRASS
            line  = CLASSIC_LINE
            forbidden = [grass, line, ball] + all_teams
            # Wider ranges to explore more vivid and dark/light options
            offside = self._find_distinct_color(
                forbidden,
                chroma=(70, 95),
                luminance=(50, 75),
                grass=grass,
                line=line,
                de_threshold=self.de_min
            )
            arrow   = self._find_distinct_color(
                forbidden + [offside],
                chroma=(70, 95),
                luminance=(45, 70),
                grass=grass,
                line=line,
                de_threshold=self.de_min    
            )

            theme = {"grass": grass, "line": line, "offside": offside, "arrow": arrow}
            self._cache[cache_key] = theme
            return theme

        # === BLACK & WHITE ===
        if mode_upper == "BLACK & WHITE":
            
            # 1. Evaluate lightness of the 4 team colors
            if majority_light(all_teams):
                grass = BW_GRASS_IF_LIGHT
                line = BW_LINE_IF_LIGHT
            else:
                grass = BW_GRASS_IF_DARK
                line = BW_LINE_IF_DARK
            
            forbidden = [grass, line, ball] + all_teams
            offside = self._find_distinct_color(
                forbidden,
                chroma=(75, 95),
                luminance=(65, 90),
                grass=grass,
                line=line,
                de_threshold=self.de_min
            )
            arrow   = self._find_distinct_color(
                forbidden + [offside],
                chroma=(75, 95),
                luminance=(45, 70),
                grass=grass,
                line=line,
                de_threshold=self.de_min
            )
            
            theme = {"grass": grass, "line": line, "offside": offside, "arrow": arrow}
            self._cache[cache_key] = theme
            return theme

        # Safety: fallback if no mode matched
        return self.fallback()

    def _find_distinct_color(
        self,
        reference_colors,
        chroma,
        luminance,
        grass: str | None = None,
        line: str | None = None,
        de_threshold = None
    ) -> str:
        """Find a color that passes filters and maximizes contrast.

        Parameters
        ----------
        reference_colors : list[str]
            Colors to avoid (teams, pitch, ball, already chosen).
        chroma : float | tuple[float, float]
            Fixed value or (min, max) for C in LCH.
        luminance : float | tuple[float, float]
            Fixed value or (min, max) for L in LCH.
        grass, line : str, optional
            Pitch surface and line colors (used for contrast checks).
        de_threshold : float
            Minimum ΔE00 between candidate and references.

        Returns
        -------
        str
            Hex color string.

        Notes
        -----
        Filters applied:
        1. ΔE > de_threshold: avoid similarity to references
        2. min contrast ratio > 1.2: ensure visibility
        3. min hue difference > 60°: avoid similar color families

        Score = min(contrast) + 0.2 * mean(contrast)
        """
        # Normalize reference list to valid hex strings
        refs = [c for c in reference_colors if isinstance(c, str) and c.startswith("#") and len(c) == 7]
        forbidden_labs = [hex_to_lab(c) for c in refs]

        best = None
        best_score = -1.0

        # Adjust luminance range based on grass color
        if grass and isinstance(luminance, tuple):
            lmin, lmax = luminance
            grass_luminance = relative_luminance(hex_to_rgb(grass))
            
            # If grass is light (white-ish), prefer dark colors
            if grass_luminance > 0.7:
                lmin, lmax = 0, 50  # Dark range
            # If grass is dark (black-ish), prefer light colors  
            elif grass_luminance < 0.3:
                lmin, lmax = 50, 100  # Light range
            # Otherwise keep original range
            luminance = (lmin, lmax)

        # Prepare L/C trials from either fixed value or (min,max) interval
        if isinstance(luminance, tuple):
            lmin, lmax = luminance
            L_trials = [lmin, (lmin + lmax) / 2.0, lmax]
        else:
            L_trials = [float(luminance)]
        if isinstance(chroma, tuple):
            cmin, cmax = chroma
            C_trials = [cmin, (cmin + cmax) / 2.0, cmax]
        else:
            C_trials = [float(chroma)]

        for step in [53, 31, 19, 11, 7]:
            candidates = []
            for L in L_trials:
                for C in C_trials:
                    for h in range(0, 360, step):
                        c_hex = lch_to_hex(L, C, h)
                        if c_hex:
                            candidates.append(c_hex)
            candidates = [c for c in candidates if c]
            for c in candidates:
                # ΔE filter against all references
                c_lab = hex_to_lab(c)
                min_de = min(delta_e_lab(c_lab, lab) for lab in forbidden_labs) if forbidden_labs else 1e9
                if min_de <= de_threshold:
                    continue
                
                # Step 1: Contrast filter - check if minimum contrast is acceptable
                contrasts = []
                if grass:
                    contrasts.append(contrast_ratio(c, grass))
                if line:
                    contrasts.append(contrast_ratio(c, line))
                for ref_hex in refs:
                    if grass and ref_hex == grass:
                        continue
                    if line and ref_hex == line:
                        continue
                    contrasts.append(contrast_ratio(c, ref_hex))
                if not contrasts:
                    continue
                
                min_cr = min(contrasts)
                avg_cr = sum(contrasts) / len(contrasts)
                
                # Reject if minimum contrast is too low
                if min_cr < 1.2:  # relaxed threshold for visibility
                    continue
                
                # Step 2: Hue difference filter - check if hue is sufficiently different
                c_lch = hex_to_lch(c)
                c_hue = c_lch[2]
                min_hue_diff = 360.0
                for ref_hex in refs:
                    ref_lch = hex_to_lch(ref_hex)
                    ref_hue = ref_lch[2]
                    hue_diff = abs(c_hue - ref_hue)
                    hue_diff = min(hue_diff, 360 - hue_diff)  # handle wrap-around
                    min_hue_diff = min(min_hue_diff, hue_diff)
                
                # Reject if hue is too similar to any forbidden color
                if min_hue_diff < 60:  # minimum 60° hue separation
                    continue
                
                # If we reach here, the color passes both filters
                # Score based on contrast quality (higher is better)
                score = min_cr + 0.2 * avg_cr 
                if score > best_score:
                    best_score = score
                    best = c


            if best is not None:
                return best

        # Nothing passed; pick vivid fallback
        return best if best else FALLBACK[2]
