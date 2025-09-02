
# ===================== Utility =====================
def fmt(x, dec=3, nd="n.d."):
    try:
        v = float(x)
        if v != v:  # check NaN
            return nd
        return f"{v:.{dec}f}" if dec > 0 else f"{v:.0f}"
    except:
        return nd