"""
Shareex Shipping Analytics Dashboard
=====================================
Run locally:
    pip install dash pandas plotly openpyxl
    python shareex_dashboard.py

Deploy to Render / Railway / Hugging Face Spaces:
    - requirements.txt  →  dash pandas plotly openpyxl gunicorn
    - start command     →  gunicorn shareex_dashboard:server
"""

import io
import base64
import datetime

import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

import dash
from dash import dcc, html, dash_table, Input, Output, State, ctx, no_update
import dash_bootstrap_components as dbc

# ─── Colour constants ─────────────────────────────────────────────────────────
NAVY   = "#1a1a2e"
GOLD   = "#f2c811"
GREEN  = "#107c10"
BLUE   = "#0078d4"
RED    = "#d83b01"
ORANGE = "#f59e0b"
PURPLE = "#5c2d91"
GRAY   = "#6b7280"

STATUS_COLOR = {
    "تم التسليم":           {"bg": "#d1e7dd", "fg": GREEN},
    "في الفرع":             {"bg": "#cce4f7", "fg": BLUE},
    "Follow":               {"bg": "#e8e3f7", "fg": PURPLE},
    "تأجيل الى تاريخ":     {"bg": "#fff4ce", "fg": "#b83b00"},
    "OH":                   {"bg": "#ffe6cc", "fg": "#c43501"},
    "Next Day":             {"bg": "#ddf2fc", "fg": "#006da3"},
    "Cancel Shipment":      {"bg": "#fde7e9", "fg": "#a80000"},
    "CR":                   {"bg": "#fde7e9", "fg": "#a80000"},
    "تحويل مكان الاستلام": {"bg": "#fff4ce", "fg": "#b83b00"},
}
PIE_COLORS = [GREEN, PURPLE, BLUE, RED, ORANGE, "#8764b8", "#008272", GRAY]

DELIVERED = "تم التسليم"
BRANCH    = "في الفرع"

# ─── Helpers ──────────────────────────────────────────────────────────────────

def norm_status(s):
    if not s or (isinstance(s, float)):
        return "Unknown"
    c = str(s).strip()
    if c.lower() == "ok":
        return DELIVERED
    if c.lower() == "branch delivered":
        return BRANCH
    return c or "Unknown"


def calc_days(pickup):
    if not pickup or str(pickup).strip() == "":
        return 0
    try:
        p = pd.to_datetime(pickup).normalize()
        return max(0, (pd.Timestamp.today().normalize() - p).days)
    except Exception:
        return 0


COLUMN_MAP = {
    "ref":      ["Ref","ref","REF","رقم الشحنة","Invoice","رقم الفاتورة"],
    "pickup":   ["Pickup","pickup","PICKUP","تاريخ الاستلام","PickupDate","تاريخ الرفع"],
    "name":     ["Name","name","Customer","الاسم","CustomerName","اسم العميل"],
    "area":     ["Area","area","منطقة","Region","المنطقة"],
    "account":  ["Account","account","الحساب","AccountName","Client","اسم الحساب"],
    "status":   ["finalstatusname","FinalStatusName","finalStatusName",
                 "Status","status","UStatus","الحالة","ShipStatus","حالة الشحنة"],
    "notes":    ["Notes","notes","ملاحظات","Comments","ملاحظات العملية"],
    "courier":  ["Courier","courier","السائق","Driver","مندوب التوصيل","المندوب"],
    "lastDate": ["lastDate","LastDate","laststatusDate","آخر تحديث"],
    "phone":    ["tel","Tel","TEL","Phone","phone","الهاتف","Mobile","رقم الهاتف","CustomerPhone"],
    "address":  ["Address","address","العنوان","CustomerAddress","عنوان العميل"],
}


def find_col(df, keys):
    for k in keys:
        if k in df.columns:
            return k
    return None


def parse_excel(contents, filename):
    """Decode uploaded file, return cleaned DataFrame."""
    content_type, content_string = contents.split(",")
    decoded = base64.b64decode(content_string)
    try:
        if filename.lower().endswith(".csv"):
            df_raw = pd.read_csv(io.StringIO(decoded.decode("utf-8")))
        else:
            df_raw = pd.read_excel(io.BytesIO(decoded))
    except Exception as e:
        return pd.DataFrame(), str(e)

    rename = {}
    for std_col, candidates in COLUMN_MAP.items():
        found = find_col(df_raw, candidates)
        if found:
            rename[found] = std_col
    df_raw.rename(columns=rename, inplace=True)

    if "ref" not in df_raw.columns:
        return pd.DataFrame(), "لم يتم العثور على عمود رقم الشحنة"

    df = df_raw.copy()
    df["ref"]     = df.get("ref", pd.Series()).astype(str).str.strip()
    df["name"]    = df.get("name", pd.Series(dtype=str)).fillna("").astype(str).str.strip()
    df["area"]    = df.get("area", pd.Series(dtype=str)).fillna("").astype(str).str.strip()
    df["account"] = df.get("account", pd.Series(dtype=str)).fillna("").astype(str).str.strip()
    df["courier"] = df.get("courier", pd.Series(dtype=str)).fillna("").astype(str).str.strip()
    df["phone"]   = df.get("phone", pd.Series(dtype=str)).fillna("").astype(str).str.strip()
    df["notes"]   = df.get("notes", pd.Series(dtype=str)).fillna("").astype(str).str.strip()
    df["status"]  = df.get("status", pd.Series(dtype=str)).apply(norm_status)

    # Parse pickup date
    if "pickup" in df.columns:
        df["pickup"] = pd.to_datetime(df["pickup"], errors="coerce").dt.date
    else:
        df["pickup"] = None

    df["days"] = df["pickup"].apply(calc_days)
    df.dropna(subset=["ref"], inplace=True)
    df = df[df["ref"] != ""]
    return df, None


def days_color(d):
    if d <= 1:  return GREEN
    if d <= 3:  return BLUE
    if d <= 5:  return ORANGE
    if d <= 7:  return "#d97706"
    return RED


# ─── KPI card builder ─────────────────────────────────────────────────────────

def kpi_card(title, value, sub="", accent=NAVY):
    return dbc.Col(
        html.Div([
            html.Div(style={
                "position":"absolute","top":0,"right":0,
                "width":"4px","height":"100%",
                "background":accent,"borderRadius":"2px 0 0 2px"
            }),
            html.P(title, style={"fontSize":"11px","color":GRAY,"marginBottom":"4px","fontWeight":"500"}),
            html.P(str(value), style={"fontSize":"28px","fontWeight":"700","color":accent,"lineHeight":"1","marginBottom":"2px"}),
            html.P(sub, style={"fontSize":"11px","color":GRAY}),
        ], style={
            "background":"#fff","border":"1px solid #e0e0e0","borderRadius":"4px",
            "padding":"14px 16px","position":"relative","overflow":"hidden"
        }),
        xs=6, md=4, xl=True
    )


# ─── App layout ───────────────────────────────────────────────────────────────

app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.BOOTSTRAP],
    suppress_callback_exceptions=True,
    title="Shareex Analytics",
    meta_tags=[{"name":"viewport","content":"width=device-width, initial-scale=1"}],
)
server = app.server   # for gunicorn

HEADER_STYLE = {
    "background": NAVY, "padding": "0 20px", "height": "44px",
    "display": "flex", "alignItems": "center", "gap": "16px",
    "position": "sticky", "top": "0", "zIndex": "1000"
}
TOOLBAR_STYLE = {
    "background": "#fff", "borderBottom": "1px solid #e0e0e0",
    "padding": "8px 20px", "display": "flex", "flexWrap": "wrap",
    "alignItems": "center", "gap": "10px", "position": "sticky", "top": "44px", "zIndex": "999"
}
CANVAS_STYLE = {"background": "#f0f2f5", "padding": "16px", "minHeight": "calc(100vh - 110px)"}

today_str = datetime.date.today().isoformat()
month_start = datetime.date.today().replace(day=1).isoformat()

app.layout = html.Div([
    # ── Data store ──
    dcc.Store(id="store-data", storage_type="session"),
    dcc.Store(id="store-notify"),

    # ── Header ──
    html.Div([
        html.Div([
            html.Div("S", style={
                "width":"28px","height":"28px","background":GOLD,"borderRadius":"4px",
                "display":"flex","alignItems":"center","justifyContent":"center",
                "fontWeight":"700","fontSize":"16px","color":NAVY
            }),
            html.Span("Shareex Analytics", style={"color":"#fff","fontWeight":"600","fontSize":"15px","marginRight":"8px"}),
        ], style={"display":"flex","alignItems":"center","gap":"8px"}),

        dbc.Tabs([
            dbc.Tab(label="نظرة عامة",  tab_id="tab-overview",  label_style={"color":"rgba(255,255,255,.6)","fontSize":"13px","padding":"0 14px","height":"44px"}, active_label_style={"color":GOLD,"borderBottom":f"2px solid {GOLD}","background":"transparent"}),
            dbc.Tab(label="الشحنات",    tab_id="tab-shipments", label_style={"color":"rgba(255,255,255,.6)","fontSize":"13px","padding":"0 14px","height":"44px"}, active_label_style={"color":GOLD,"borderBottom":f"2px solid {GOLD}","background":"transparent"}),
            dbc.Tab(label="المناديب",   tab_id="tab-drivers",   label_style={"color":"rgba(255,255,255,.6)","fontSize":"13px","padding":"0 14px","height":"44px"}, active_label_style={"color":GOLD,"borderBottom":f"2px solid {GOLD}","background":"transparent"}),
            dbc.Tab(label="التقادم",    tab_id="tab-aging",     label_style={"color":"rgba(255,255,255,.6)","fontSize":"13px","padding":"0 14px","height":"44px"}, active_label_style={"color":GOLD,"borderBottom":f"2px solid {GOLD}","background":"transparent"}),
        ], id="tabs", active_tab="tab-overview",
           style={"flex":"1","borderBottom":"none","background":"transparent"}),

        html.Span(id="last-update", style={"color":"rgba(255,255,255,.4)","fontSize":"11px","marginRight":"auto"}),
    ], style=HEADER_STYLE),

    # ── Toolbar ──
    html.Div([
        dcc.Upload(
            id="upload",
            children=html.Button("⬆ رفع Excel", style={
                "background":GOLD,"color":NAVY,"border":f"1px solid {GOLD}",
                "borderRadius":"3px","padding":"5px 12px","fontSize":"12px",
                "fontWeight":"600","cursor":"pointer"
            }),
            accept=".xlsx,.xls,.csv", multiple=False,
        ),
        html.Button("⬇ تصدير", id="btn-export", n_clicks=0, style={
            "background":"#fff","border":"1px solid #ccc","borderRadius":"3px",
            "padding":"5px 10px","fontSize":"12px","cursor":"pointer","color":"#333"
        }),
        dcc.Download(id="download"),

        html.Div(style={"width":"1px","height":"22px","background":"#e0e0e0"}),

        # Date presets
        html.Div([
            html.Button("اليوم",  id="btn-today", n_clicks=0, className="preset-btn"),
            html.Button("7 أيام", id="btn-week",  n_clicks=0, className="preset-btn"),
            html.Button("الشهر",  id="btn-month", n_clicks=0, className="preset-btn"),
            html.Button("الكل",   id="btn-all",   n_clicks=0, className="preset-btn"),
        ], style={"display":"flex","gap":"2px","background":"#f7f7f7","border":"1px solid #ddd","borderRadius":"3px","padding":"2px"}),

        dcc.DatePickerRange(
            id="date-range",
            start_date=month_start, end_date=today_str,
            display_format="DD/MM/YYYY",
            style={"fontSize":"12px"},
        ),

        dcc.Dropdown(id="status-filter", placeholder="كل الحالات",
                     style={"minWidth":"160px","fontSize":"12px","direction":"rtl"},
                     clearable=True),

        dbc.Input(id="search-box", placeholder="🔍 بحث...",
                  debounce=True, style={"maxWidth":"200px","fontSize":"12px","height":"34px"}),
    ], style=TOOLBAR_STYLE),

    # ── Notification ──
    dbc.Toast(id="notify", is_open=False, duration=3500,
              style={"position":"fixed","bottom":"20px","left":"50%","transform":"translateX(-50%)","zIndex":9999,"minWidth":"260px"}),

    # ── Page content ──
    html.Div(id="page-content", style=CANVAS_STYLE),

    # CSS overrides
    html.Style("""
        @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700&display=swap');
        body { font-family: 'Cairo', 'Segoe UI', sans-serif !important; direction: rtl; background: #f0f2f5; }
        .nav-tabs { border-bottom: none !important; }
        .nav-link { height: 44px !important; display: flex !important; align-items: center !important; }
        .preset-btn {
            background: transparent; border: none; border-radius: 2px;
            padding: 3px 10px; font-size: 11px; cursor: pointer; color: #555; font-weight: 500;
        }
        .preset-btn:hover { background: #e8e8e8; }
        .preset-btn.active { background: #1a1a2e; color: #f2c811; }
        .tab-content { background: transparent !important; }
        .DateRangePickerInput { font-size: 12px !important; }
        .Select-control { font-size: 12px !important; }
        td, th { font-size: 12px !important; }
    """),
], style={"direction":"rtl"})


# ─── Callbacks ────────────────────────────────────────────────────────────────

@app.callback(
    Output("store-data", "data"),
    Output("notify", "children"),
    Output("notify", "is_open"),
    Output("notify", "color"),
    Output("last-update", "children"),
    Output("status-filter", "options"),
    Input("upload", "contents"),
    State("upload", "filename"),
    State("store-data", "data"),
    prevent_initial_call=True,
)
def upload_file(contents, filename, existing_data):
    if not contents:
        return no_update, no_update, no_update, no_update, no_update, no_update

    df_new, err = parse_excel(contents, filename)
    if err:
        return no_update, f"خطأ: {err}", True, "danger", no_update, no_update

    df_new["pickup"] = df_new["pickup"].astype(str)

    if existing_data:
        df_old = pd.DataFrame(existing_data)
        added = 0; updated = 0
        df_old.set_index("ref", inplace=True)
        for _, row in df_new.iterrows():
            if row["ref"] in df_old.index:
                if df_old.at[row["ref"], "status"] != row["status"]:
                    df_old.loc[row["ref"]] = row.values
                    updated += 1
            else:
                df_old = pd.concat([df_old, row.to_frame().T.set_index("ref")])
                added += 1
        df_final = df_old.reset_index()
        msg = f"✅ {added} جديد · {updated} محدّث"
    else:
        df_final = df_new
        msg = f"✅ تم تحميل {len(df_final):,} شحنة"

    opts = [{"label": s, "value": s} for s in sorted(df_final["status"].dropna().unique())]
    ts = datetime.datetime.now().strftime("%H:%M")
    return df_final.to_dict("records"), msg, True, "success", f"آخر تحديث: {ts}", opts


@app.callback(
    Output("date-range", "start_date"),
    Output("date-range", "end_date"),
    Input("btn-today", "n_clicks"),
    Input("btn-week",  "n_clicks"),
    Input("btn-month", "n_clicks"),
    Input("btn-all",   "n_clicks"),
    prevent_initial_call=True,
)
def date_presets(*_):
    triggered = ctx.triggered_id
    t = datetime.date.today()
    if triggered == "btn-today":
        return t.isoformat(), t.isoformat()
    if triggered == "btn-week":
        return (t - datetime.timedelta(days=6)).isoformat(), t.isoformat()
    if triggered == "btn-month":
        return t.replace(day=1).isoformat(), t.isoformat()
    return "2020-01-01", t.isoformat()


def apply_filters(records, start, end, status_val, search_q):
    if not records:
        return pd.DataFrame()
    df = pd.DataFrame(records)
    if start:
        df = df[df["pickup"] >= start]
    if end:
        df = df[df["pickup"] <= end]
    if status_val:
        df = df[df["status"] == status_val]
    if search_q:
        q = search_q.lower()
        mask = df[["ref","name","account","area","courier","phone"]].apply(
            lambda col: col.astype(str).str.lower().str.contains(q, na=False)
        ).any(axis=1)
        df = df[mask]
    return df


@app.callback(
    Output("page-content", "children"),
    Input("tabs", "active_tab"),
    Input("store-data", "data"),
    Input("date-range", "start_date"),
    Input("date-range", "end_date"),
    Input("status-filter", "value"),
    Input("search-box", "value"),
)
def render_page(active_tab, records, start, end, status_val, search_q):
    df = apply_filters(records, start, end, status_val, search_q)
    empty = df.empty

    total     = len(df)
    ok_count  = len(df[df["status"] == DELIVERED]) if not empty else 0
    br_count  = len(df[df["status"] == BRANCH])    if not empty else 0
    late      = len(df[(df["status"] != DELIVERED) & (df["status"] != BRANCH) & (df["days"] > 7)]) if not empty else 0
    drivers_n = df["courier"].nunique() if not empty else 0
    rate      = round(ok_count / total * 100) if total else 0
    unique_days = df["pickup"].nunique() if not empty else 0
    velocity  = round(total / unique_days) if unique_days else 0
    all_total = len(records) if records else 0

    # ── Overview page ──────────────────────────────────────────────────────────
    if active_tab == "tab-overview":
        kpi_row = dbc.Row([
            kpi_card("إجمالي الشحنات",   f"{total:,}",   f"{all_total:,} إجمالي", NAVY),
            kpi_card("تم التسليم",       f"{ok_count:,}", f"{rate}% معدل النجاح",  GREEN),
            kpi_card("في الفرع",         f"{br_count:,}", "Branch Delivered",        BLUE),
            kpi_card("متأخر (+7 أيام)",  f"{late:,}",    "يحتاج متابعة" if late else "ممتاز", RED),
            kpi_card("شحنة / يوم",       f"{velocity}",  f"{unique_days} يوم نشط",  PURPLE),
        ], className="g-3 mb-3")

        # Trend chart
        if not empty and "pickup" in df.columns:
            trend_df = df.groupby("pickup").agg(
                total=("ref","count"),
                delivered=("status", lambda x: (x == DELIVERED).sum())
            ).reset_index()
            trend_df["other"] = trend_df["total"] - trend_df["delivered"]
            fig_trend = go.Figure()
            fig_trend.add_trace(go.Scatter(
                x=trend_df["pickup"], y=trend_df["total"], name="الإجمالي",
                mode="lines+markers", line=dict(color=NAVY, width=2),
                fill="tozeroy", fillcolor="rgba(26,26,46,0.07)"
            ))
            fig_trend.add_trace(go.Scatter(
                x=trend_df["pickup"], y=trend_df["delivered"], name="تم التسليم",
                mode="lines+markers", line=dict(color=GREEN, width=2, dash="dot"),
                fill="tozeroy", fillcolor="rgba(16,124,16,0.08)"
            ))
            fig_trend.update_layout(**chart_layout("اتجاه الشحنات اليومي"))
        else:
            fig_trend = empty_fig("لا توجد بيانات")

        # Pie chart
        if not empty:
            status_counts = df["status"].value_counts().reset_index()
            status_counts.columns = ["status", "count"]
            top5 = status_counts.head(5)
            if len(status_counts) > 5:
                rest = pd.DataFrame([{"status": "أخرى", "count": status_counts.iloc[5:]["count"].sum()}])
                top5 = pd.concat([top5, rest], ignore_index=True)
            fig_pie = go.Figure(go.Pie(
                labels=top5["status"], values=top5["count"],
                hole=0.55, marker_colors=PIE_COLORS[:len(top5)],
                textinfo="percent", textfont_size=11
            ))
            fig_pie.update_layout(**chart_layout("توزيع الحالات"))
        else:
            fig_pie = empty_fig("لا توجد بيانات")

        # Top drivers bar
        if not empty and "courier" in df.columns:
            drv = df.groupby("courier").agg(
                total=("ref","count"),
                ok=("status", lambda x: (x==DELIVERED).sum())
            ).reset_index()
            drv["rate"] = (drv["ok"] / drv["total"] * 100).round().astype(int)
            drv = drv.sort_values("rate", ascending=False).head(8)
            drv["color"] = drv["rate"].apply(lambda r: GREEN if r>=80 else (ORANGE if r>=50 else RED))
            fig_drv = go.Figure(go.Bar(
                x=drv["rate"], y=drv["courier"], orientation="h",
                marker_color=drv["color"], text=drv["rate"].astype(str)+"%",
                textposition="auto", textfont_size=11
            ))
            fig_drv.update_layout(**chart_layout("أفضل المناديب (% تسليم)"))
            fig_drv.update_xaxes(range=[0, 110], showgrid=True, gridcolor="#f0f0f0")
        else:
            fig_drv = empty_fig("لا توجد بيانات")

        charts_row = dbc.Row([
            dbc.Col(dbc.Card([dbc.CardBody(dcc.Graph(figure=fig_trend, config={"displayModeBar":False}, style={"height":"260px"}))], style=card_style()), lg=6),
            dbc.Col(dbc.Card([dbc.CardBody(dcc.Graph(figure=fig_pie,   config={"displayModeBar":False}, style={"height":"260px"}))], style=card_style()), lg=3),
            dbc.Col(dbc.Card([dbc.CardBody(dcc.Graph(figure=fig_drv,   config={"displayModeBar":False}, style={"height":"260px"}))], style=card_style()), lg=3),
        ], className="g-3 mb-3")

        # Status breakdown bar
        if not empty:
            sb = df["status"].value_counts().reset_index()
            sb.columns = ["status","count"]
            sb["color"] = sb["status"].apply(lambda s: STATUS_COLOR.get(s,{}).get("fg", GRAY))
            fig_sb = go.Figure(go.Bar(
                x=sb["count"], y=sb["status"], orientation="h",
                marker_color=sb["color"], text=sb["count"],
                textposition="auto", textfont_size=11
            ))
            fig_sb.update_layout(**chart_layout("توزيع تفصيلي للحالات"))
            fig_sb.update_xaxes(showgrid=True, gridcolor="#f0f0f0")
        else:
            fig_sb = empty_fig("لا توجد بيانات")

        bar_row = dbc.Row([
            dbc.Col(dbc.Card([dbc.CardBody(dcc.Graph(figure=fig_sb, config={"displayModeBar":False}, style={"height":"300px"}))], style=card_style()), lg=12),
        ], className="g-3")

        return html.Div([kpi_row, charts_row, bar_row])

    # ── Shipments page ─────────────────────────────────────────────────────────
    if active_tab == "tab-shipments":
        kpi_row = dbc.Row([
            kpi_card("المعروض",      f"{total:,}",    "شحنة",               NAVY),
            kpi_card("تم التسليم",  f"{ok_count:,}",  f"{rate}%",           GREEN),
            kpi_card("في الفرع",    f"{br_count:,}",  "Branch Delivered",    BLUE),
            kpi_card("متأخر",       f"{late:,}",      "+7 أيام",             RED),
            kpi_card("المناديب",    f"{drivers_n:,}", "مندوب نشط",          PURPLE),
        ], className="g-3 mb-3")

        if empty:
            table_content = html.Div([
                html.Div("لا توجد بيانات", style={"textAlign":"center","padding":"60px","color":GRAY,"fontSize":"14px"})
            ])
        else:
            tbl_df = df[["ref","name","phone","account","area","pickup","status","days","courier"]].copy()
            tbl_df.columns = ["رقم الشحنة","العميل","الهاتف","الحساب","المنطقة","تاريخ الاستلام","الحالة","الأيام","المندوب"]
            tbl_df = tbl_df.head(500)   # cap for performance

            table_content = dash_table.DataTable(
                data=tbl_df.to_dict("records"),
                columns=[{"name": c, "id": c} for c in tbl_df.columns],
                page_size=20,
                filter_action="native",
                sort_action="native",
                style_table={"overflowX":"auto","borderRadius":"4px"},
                style_header={
                    "backgroundColor": NAVY, "color": GOLD,
                    "fontWeight": "600", "fontSize": "11px",
                    "border": "none", "textAlign": "right", "padding": "10px"
                },
                style_cell={
                    "textAlign": "right", "fontSize": "12px",
                    "padding": "8px 10px", "border": "1px solid #f0f0f0",
                    "fontFamily": "Cairo, Segoe UI, sans-serif",
                    "maxWidth": "150px", "overflow": "hidden",
                    "textOverflow": "ellipsis", "whiteSpace": "nowrap",
                },
                style_data_conditional=[
                    {"if": {"row_index": "odd"}, "backgroundColor": "#fafafa"},
                    {"if": {"filter_query": "{الحالة} = 'تم التسليم'", "column_id": "الحالة"},
                     "color": GREEN, "fontWeight": "700"},
                    {"if": {"filter_query": "{الحالة} = 'في الفرع'", "column_id": "الحالة"},
                     "color": BLUE, "fontWeight": "700"},
                    {"if": {"filter_query": "{الأيام} > 7", "column_id": "الأيام"},
                     "color": RED, "fontWeight": "700"},
                ],
                style_as_list_view=False,
            )

        return html.Div([
            kpi_row,
            dbc.Card([dbc.CardBody([
                html.Div([
                    html.Span("جدول الشحنات", style={"fontWeight":"700","fontSize":"14px","color":NAVY}),
                    html.Span(f" — {total:,} شحنة", style={"color":GRAY,"fontSize":"12px"})
                ], style={"marginBottom":"12px"}),
                table_content
            ])], style=card_style())
        ])

    # ── Drivers page ───────────────────────────────────────────────────────────
    if active_tab == "tab-drivers":
        if not records:
            return no_data_page()

        all_df = pd.DataFrame(records)
        drv = all_df.groupby("courier").agg(
            total=("ref","count"),
            ok=("status", lambda x: (x==DELIVERED).sum()),
            branch=("status", lambda x: (x==BRANCH).sum()),
            late=("days", lambda x: ((all_df.loc[x.index,"status"] != DELIVERED) &
                                      (all_df.loc[x.index,"status"] != BRANCH) &
                                      (all_df.loc[x.index,"days"] > 7)).sum()),
        ).reset_index()
        drv["rate"]  = (drv["ok"] / drv["total"] * 100).round().astype(int)
        drv["rate%"] = drv["rate"].astype(str) + "%"
        drv = drv.sort_values("rate", ascending=False).reset_index(drop=True)

        top1  = drv.iloc[0] if len(drv) > 0 else None
        worst = drv.iloc[-1] if len(drv) > 1 else None

        kpi_row = dbc.Row([
            kpi_card("عدد المناديب",      f"{len(drv):,}",          "مندوب",          NAVY),
            kpi_card("إجمالي تسليم",      f"{drv['ok'].sum():,}",   "شحنة مسلّمة",    GREEN),
            kpi_card("في الفرع",          f"{drv['branch'].sum():,}","شحنة",            BLUE),
            kpi_card("أعلى معدل",         f"{top1['rate']}%" if top1 is not None else "—",   str(top1["courier"])[:18] if top1 is not None else "—", GREEN),
            kpi_card("أقل معدل",          f"{worst['rate']}%" if worst is not None else "—",  str(worst["courier"])[:18] if worst is not None else "—", RED),
        ], className="g-3 mb-3")

        # Driver performance horizontal bar
        fig_d = go.Figure()
        fig_d.add_trace(go.Bar(
            y=drv["courier"], x=drv["ok"], name="تم التسليم",
            orientation="h", marker_color=GREEN, text=drv["ok"],
            textposition="inside", textfont_size=10
        ))
        fig_d.add_trace(go.Bar(
            y=drv["courier"], x=drv["branch"], name="في الفرع",
            orientation="h", marker_color=BLUE, text=drv["branch"],
            textposition="inside", textfont_size=10
        ))
        fig_d.add_trace(go.Bar(
            y=drv["courier"], x=drv["total"]-drv["ok"]-drv["branch"], name="أخرى",
            orientation="h", marker_color="#e0e0e0"
        ))
        fig_d.update_layout(**chart_layout("أداء المناديب — توزيع الشحنات"), barmode="stack")

        # Rate scatter
        fig_r = go.Figure(go.Bar(
            x=drv["rate"], y=drv["courier"], orientation="h",
            marker_color=drv["rate"].apply(lambda r: GREEN if r>=80 else (ORANGE if r>=50 else RED)),
            text=drv["rate%"], textposition="auto", textfont_size=11
        ))
        fig_r.update_layout(**chart_layout("معدل نجاح كل مندوب (%)"))
        fig_r.update_xaxes(range=[0,110], showgrid=True, gridcolor="#f0f0f0")

        tbl_df2 = drv.rename(columns={
            "courier":"المندوب","total":"الإجمالي","ok":"تم التسليم",
            "branch":"في الفرع","late":"متأخر","rate%":"النسبة"
        })[["المندوب","الإجمالي","تم التسليم","في الفرع","متأخر","النسبة"]]

        return html.Div([
            kpi_row,
            dbc.Row([
                dbc.Col(dbc.Card([dbc.CardBody(dcc.Graph(figure=fig_d, config={"displayModeBar":False},
                        style={"height": f"{max(280, len(drv)*35)}px"}))], style=card_style()), lg=6),
                dbc.Col(dbc.Card([dbc.CardBody(dcc.Graph(figure=fig_r, config={"displayModeBar":False},
                        style={"height": f"{max(280, len(drv)*35)}px"}))], style=card_style()), lg=6),
            ], className="g-3 mb-3"),
            dbc.Card([dbc.CardBody([
                html.Span("جدول تفصيلي", style={"fontWeight":"700","fontSize":"14px","color":NAVY,"display":"block","marginBottom":"10px"}),
                dash_table.DataTable(
                    data=tbl_df2.to_dict("records"),
                    columns=[{"name":c,"id":c} for c in tbl_df2.columns],
                    sort_action="native", page_size=20,
                    style_table={"overflowX":"auto"},
                    style_header={"backgroundColor":NAVY,"color":GOLD,"fontWeight":"600","fontSize":"11px","textAlign":"right","padding":"10px"},
                    style_cell={"textAlign":"right","fontSize":"12px","padding":"8px 10px","border":"1px solid #f0f0f0","fontFamily":"Cairo,Segoe UI,sans-serif"},
                    style_data_conditional=[
                        {"if":{"row_index":"odd"},"backgroundColor":"#fafafa"},
                        {"if":{"column_id":"تم التسليم"},"color":GREEN,"fontWeight":"700"},
                        {"if":{"column_id":"في الفرع"},"color":BLUE,"fontWeight":"700"},
                        {"if":{"column_id":"متأخر"},"color":RED,"fontWeight":"700"},
                    ],
                )
            ])], style=card_style()),
        ])

    # ── Aging page ─────────────────────────────────────────────────────────────
    if active_tab == "tab-aging":
        aging_df = df[(df["status"] != DELIVERED) & (df["status"] != BRANCH)] if not empty else pd.DataFrame()

        bins   = [0, 3, 7, 14, 21, 999]
        labels_age = ["1–3 أيام", "4–7 أيام", "8–14 يوم", "15–21 يوم", "+21 يوم"]
        colors_age = [GREEN, BLUE, ORANGE, "#d97706", RED]

        kpi_ok  = ok_count
        kpi_br  = br_count
        aging_count = len(aging_df)
        kpi_row = dbc.Row([
            kpi_card("تم التسليم",        f"{kpi_ok:,}", f"{rate}%",      GREEN),
            kpi_card("في الفرع",          f"{kpi_br:,}", "غير مسلّم",     BLUE),
            kpi_card("قيد التشغيل",       f"{aging_count:,}", "شحنة نشطة", ORANGE),
            kpi_card("متأخر جداً (+14)", f"{len(aging_df[aging_df['days']>14]):,}" if not aging_df.empty else "0", "يحتاج تدخل", RED),
            kpi_card("متوسط الأيام",      f"{round(aging_df['days'].mean()) if not aging_df.empty else 0}", "يوم", PURPLE),
        ], className="g-3 mb-3")

        if not aging_df.empty:
            aging_df = aging_df.copy()
            aging_df["bucket"] = pd.cut(aging_df["days"], bins=bins, labels=labels_age, right=True)
            bucket_counts = aging_df["bucket"].value_counts().reindex(labels_age, fill_value=0).reset_index()
            bucket_counts.columns = ["الفئة","العدد"]

            fig_aging = go.Figure(go.Bar(
                x=bucket_counts["الفئة"], y=bucket_counts["العدد"],
                marker_color=colors_age,
                text=bucket_counts["العدد"], textposition="outside",
            ))
            fig_aging.update_layout(**chart_layout("توزيع التقادم — فئات الأيام"))

            # By status
            s_counts = aging_df["status"].value_counts().reset_index()
            s_counts.columns = ["status","count"]
            s_counts["color"] = s_counts["status"].apply(lambda s: STATUS_COLOR.get(s,{}).get("fg", GRAY))
            fig_s = go.Figure(go.Bar(
                x=s_counts["count"], y=s_counts["status"], orientation="h",
                marker_color=s_counts["color"], text=s_counts["count"], textposition="auto"
            ))
            fig_s.update_layout(**chart_layout("حالات الشحنات غير المسلّمة"))

            tbl_aging = aging_df[["ref","name","phone","area","pickup","status","days","courier"]].sort_values("days", ascending=False).head(200)
            tbl_aging.columns = ["رقم الشحنة","العميل","الهاتف","المنطقة","تاريخ الاستلام","الحالة","الأيام","المندوب"]

            table_aging = dash_table.DataTable(
                data=tbl_aging.to_dict("records"),
                columns=[{"name":c,"id":c} for c in tbl_aging.columns],
                page_size=20, sort_action="native", filter_action="native",
                style_table={"overflowX":"auto"},
                style_header={"backgroundColor":NAVY,"color":GOLD,"fontWeight":"600","fontSize":"11px","textAlign":"right","padding":"10px"},
                style_cell={"textAlign":"right","fontSize":"12px","padding":"8px 10px","border":"1px solid #f0f0f0","fontFamily":"Cairo,Segoe UI,sans-serif"},
                style_data_conditional=[
                    {"if":{"row_index":"odd"},"backgroundColor":"#fafafa"},
                    {"if":{"filter_query":"{الأيام} > 14","column_id":"الأيام"},"color":RED,"fontWeight":"700"},
                    {"if":{"filter_query":"{الأيام} > 7","column_id":"الأيام"},"color":ORANGE,"fontWeight":"600"},
                ],
            )
        else:
            fig_aging = empty_fig("لا توجد بيانات")
            fig_s     = empty_fig("لا توجد بيانات")
            table_aging = html.Div("لا توجد بيانات", style={"textAlign":"center","padding":"40px","color":GRAY})

        return html.Div([
            kpi_row,
            dbc.Row([
                dbc.Col(dbc.Card([dbc.CardBody(dcc.Graph(figure=fig_aging, config={"displayModeBar":False}, style={"height":"280px"}))], style=card_style()), lg=7),
                dbc.Col(dbc.Card([dbc.CardBody(dcc.Graph(figure=fig_s,     config={"displayModeBar":False}, style={"height":"280px"}))], style=card_style()), lg=5),
            ], className="g-3 mb-3"),
            dbc.Card([dbc.CardBody([
                html.Span("الشحنات غير المسلّمة — مرتّبة من الأقدم", style={"fontWeight":"700","fontSize":"14px","color":NAVY,"display":"block","marginBottom":"10px"}),
                table_aging
            ])], style=card_style()),
        ])

    return html.Div()


@app.callback(
    Output("download", "data"),
    Input("btn-export", "n_clicks"),
    State("store-data", "data"),
    State("date-range", "start_date"),
    State("date-range", "end_date"),
    State("status-filter", "value"),
    State("search-box", "value"),
    prevent_initial_call=True,
)
def export_excel(n, records, start, end, status_val, search_q):
    if not n or not records:
        return no_update
    df = apply_filters(records, start, end, status_val, search_q)
    if df.empty:
        return no_update
    export_cols = ["ref","name","phone","account","area","pickup","status","days","courier","notes"]
    export_df = df[[c for c in export_cols if c in df.columns]].copy()
    export_df.columns = [{"ref":"رقم الشحنة","name":"العميل","phone":"الهاتف",
        "account":"الحساب","area":"المنطقة","pickup":"تاريخ الاستلام",
        "status":"الحالة","days":"الأيام","courier":"المندوب","notes":"ملاحظات"}.get(c,c)
        for c in export_df.columns]
    fname = f"Shareex_{datetime.date.today().isoformat()}.xlsx"
    return dcc.send_data_frame(export_df.to_excel, fname, index=False, sheet_name="Shareex")


# ─── Layout helpers ───────────────────────────────────────────────────────────

def chart_layout(title=""):
    return dict(
        title=dict(text=title, font=dict(size=13, color=NAVY, family="Cairo"), x=0, xanchor="left"),
        margin=dict(l=10, r=10, t=40, b=10),
        paper_bgcolor="white", plot_bgcolor="white",
        font=dict(family="Cairo, Segoe UI, sans-serif", size=11, color="#555"),
        legend=dict(orientation="h", y=-0.18, font_size=11),
        xaxis=dict(showgrid=True, gridcolor="#f0f0f0", zeroline=False),
        yaxis=dict(showgrid=False, zeroline=False),
    )


def empty_fig(msg="لا توجد بيانات"):
    fig = go.Figure()
    fig.update_layout(
        annotations=[dict(text=msg, x=0.5, y=0.5, xref="paper", yref="paper",
                         showarrow=False, font=dict(size=14, color=GRAY))],
        **chart_layout()
    )
    return fig


def card_style():
    return {"border":"1px solid #e0e0e0","borderRadius":"4px","boxShadow":"none","background":"#fff"}


def no_data_page():
    return html.Div("لا توجد بيانات — ارفع ملف Excel للبدء",
                    style={"textAlign":"center","padding":"80px","color":GRAY,"fontSize":"14px"})


# ─── Run ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=8050)
