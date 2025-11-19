import hashlib
from pathlib import Path
from datetime import timedelta

import mysql.connector
from mysql.connector import Error
import pandas as pd
import plotly.express as px
import streamlit as st

from components.animations import inject_animations

DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "",  # Remplacez par votre mot de passe MySQL
    "database": "smart_market",
}

MAX_UPLOAD_BYTES = 1_000_000_000  # 1 Go
MAX_UPLOAD_MB = MAX_UPLOAD_BYTES // (1024 * 1024)


def _asset_or_remote(name: str, remote_url: str):
    """Helper pour charger une image locale ou distante"""
    p = Path(__file__).parent / "assets" / name
    return str(p) if p.exists() else remote_url


IMAGES = {
    "hero": _asset_or_remote(
        "hero_market.jpg",
        "https://images.unsplash.com/photo-1504384308090-c894fdcc538d?auto=format&fit=crop&w=1600&q=80",
    ),
    "analytics": _asset_or_remote(
        "analytics.jpg",
        "https://images.unsplash.com/photo-1551288049-bebda4e38f71?auto=format&fit=crop&w=800&q=80",
    ),
    "dashboard": _asset_or_remote(
        "dashboard.jpg",
        "https://images.unsplash.com/photo-1551434678-e076c223a692?auto=format&fit=crop&w=800&q=80",
    ),
    "dashboard_hero": _asset_or_remote(
        "dashboard_banner.jpg",
        "https://images.unsplash.com/photo-1520607162513-77705c0f0d4a?auto=format&fit=crop&w=1600&q=80",
    ),
    "team": _asset_or_remote(
        "team.jpg",
        "https://images.unsplash.com/photo-1522202176988-66273c2fd55f?auto=format&fit=crop&w=800&q=80",
    ),
    "insights": _asset_or_remote(
        "insights.jpg",
        "https://images.unsplash.com/photo-1508385082359-fb06f13b8a3f?auto=format&fit=crop&w=800&q=80",
    ),
    "sales": _asset_or_remote(
        "sales.jpg",
        "https://images.unsplash.com/photo-1485217988980-11786ced9454?auto=format&fit=crop&w=800&q=80",
    ),
    "home": _asset_or_remote(
        "home.jpg",
        "https://images.unsplash.com/photo-1556740749-887f6717d7e4?auto=format&fit=crop&w=1600&q=80",
    ),
    "upload": _asset_or_remote(
        "upload.jpg",
        "https://images.unsplash.com/photo-1489515217757-5fd1be406fef?auto=format&fit=crop&w=1600&q=80",
    ),
    "prediction": _asset_or_remote(
        "prediction.jpg",
        "https://images.unsplash.com/photo-1504384308090-c894fdcc538d?auto=format&fit=crop&w=1600&q=80",
    ),
}


def create_menu():
    """Crée le menu de navigation avec le bouton de connexion"""
    menu_container = st.container()
    with menu_container:
        menu_cols = st.columns([6, 1, 1])

        with menu_cols[0]:
            st.write("")

        with menu_cols[1]:
            st.write("")
        with menu_cols[2]:
            if st.session_state.get("authenticated", False):
                user_menu = st.expander(f"👤 {st.session_state.get('username', '')}")
                with user_menu:
                    st.markdown("### Menu utilisateur")
                    if "theme" not in st.session_state:
                        st.session_state.theme = "light"
                    theme_icon = "🌙" if st.session_state.theme == "light" else "☀️"
                    if st.button(
                        f"{theme_icon} Thème {st.session_state.theme.capitalize()}",
                        key="home_theme_button",
                    ):
                        st.session_state.theme = (
                            "dark" if st.session_state.theme == "light" else "light"
                        )
                    if st.button("📤 Déconnexion", key="home_logout_button"):
                        st.session_state.authenticated = False
                        st.session_state.username = ""
                        st.session_state.is_authenticated = False
                        st.session_state.user_email = ""
                        st.experimental_rerun()

        st.markdown("---")


def _get_connection():
    """Retourne une connexion MySQL ou lève une erreur."""
    return mysql.connector.connect(**DB_CONFIG)


def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def verify_credentials(email: str, password: str):
    """Retourne l'e-mail si les identifiants sont valides."""
    connection = None
    try:
        connection = _get_connection()
        cursor = connection.cursor()
        query = "SELECT email FROM users WHERE email = %s AND password_hash = %s"
        cursor.execute(query, (email, _hash_password(password)))
        result = cursor.fetchone()
        return result[0] if result else None
    except Error as e:
        st.error(f"Erreur lors de la connexion à la base de données : {e}")
        return None
    finally:
        if connection and connection.is_connected():
            cursor.close()
            connection.close()


def register_user(email: str, password: str) -> bool:
    """Crée un utilisateur. Retourne True si l'inscription réussit."""
    connection = None
    try:
        connection = _get_connection()
        cursor = connection.cursor()
        query = "INSERT INTO users (email, password_hash) VALUES (%s, %s)"
        cursor.execute(query, (email, _hash_password(password)))
        connection.commit()
        return True
    except Error as e:
        st.error(f"Erreur lors de l'inscription : {e}")
        return False
    finally:
        if connection and connection.is_connected():
            cursor.close()
            connection.close()


# -------------------------- Helpers dashboard dynamiques ------------------
def check_data():
    if "data" not in st.session_state:
        st.warning("⚠️ Importez d'abord un dataset depuis la section Téléversement.")
        return False
    return True


def _find_column(df, keywords):
    cols = list(df.columns)
    lowered = [c.lower() for c in cols]
    for kw in keywords:
        for idx, name in enumerate(lowered):
            if kw in name:
                return cols[idx]
    return None


def _is_date_like(series: pd.Series, sample=200):
    if pd.api.types.is_datetime64_any_dtype(series):
        return True
    try:
        values = series.dropna().astype(str)
        if values.empty:
            return False
        sample_values = values.sample(min(len(values), sample), random_state=42)
        parsed = pd.to_datetime(sample_values, errors="coerce")
        return parsed.notna().mean() > 0.6
    except Exception:
        return False


def detect_sales_columns(df: pd.DataFrame):
    df = df.copy()
    cols = df.columns
    date_col = next((c for c in cols if _is_date_like(df[c])), None)
    revenue_col = _find_column(df, ["revenue", "amount", "total", "sales", "price", "montant"])
    qty_col = _find_column(df, ["quantity", "qty", "units", "unit", "quantité", "qte"])
    product_col = _find_column(df, ["product", "item", "sku", "article", "produit"])
    store_col = _find_column(df, ["store", "shop", "branch", "location", "magasin"])
    order_col = _find_column(df, ["order_id", "order", "invoice", "transaction", "commande"])
    customer_col = _find_column(df, ["customer", "client", "buyer", "client_id"])

    if revenue_col is None and qty_col:
        price_col = _find_column(df, ["price", "unit_price", "cost", "prix"])
        if price_col:
            try:
                df["_computed_revenue"] = pd.to_numeric(df[price_col], errors="coerce") * pd.to_numeric(
                    df[qty_col], errors="coerce"
                )
                revenue_col = "_computed_revenue"
            except Exception:
                revenue_col = None

    if date_col:
        df[date_col] = pd.to_datetime(df[date_col], errors="coerce")

    return {
        "df": df,
        "date_col": date_col,
        "revenue_col": revenue_col,
        "qty_col": qty_col,
        "product_col": product_col,
        "store_col": store_col,
        "order_col": order_col,
        "customer_col": customer_col,
    }


def fmt_currency(value, currency_label="GNF"):
    if value is None:
        return "N/A"
    try:
        return f"{int(value):,} {currency_label}"
    except Exception:
        return str(value)


def fmt_number(value):
    if value is None:
        return "N/A"
    try:
        return f"{int(value):,}"
    except Exception:
        return str(value)


@st.cache_data(ttl=300)
def compute_time_series(df: pd.DataFrame, date_col: str, value_col: str, freq="D"):
    subset = df[[date_col, value_col]].dropna()
    if subset.empty:
        return pd.DataFrame()
    subset = subset.assign(date=pd.to_datetime(subset[date_col]).dt.floor(freq))
    aggregated = subset.groupby("date")[value_col].sum().reset_index().sort_values("date")
    return aggregated


def render_home_page():
    inject_animations()
    st.session_state.setdefault("theme", "light")
    st.session_state.setdefault("authenticated", False)
    st.session_state["authenticated"] = st.session_state.get("is_authenticated", False)
    if st.session_state.get("user_email"):
        st.session_state["username"] = st.session_state.get("user_email", "")

    st.markdown(
        f"""
        <style>
        :root {{
            --hero-img: url('{IMAGES['hero']}');
        }}
        .hero-section {{
            position: relative;
            margin: -4rem -4rem 2rem -4rem;
            padding: 6rem 2rem;
            background: linear-gradient(rgba(0,0,0,0.45), rgba(0,0,0,0.45)), var(--hero-img);
            background-size: cover;
            background-position: center;
            color: white;
            border-radius: 0;
            text-align: center;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            min-height: 420px;
            background-attachment: scroll;
        }}

        .feature-grid {{
            display: flex;
            flex-wrap: wrap;
            gap: 1.5rem;
            margin-bottom: 2rem;
            justify-content: center;
        }}

        .feature-card {{
            background: white;
            padding: 1.75rem;
            border-radius: 16px;
            box-shadow: 0 12px 30px rgba(15, 23, 42, 0.08);
            display: flex;
            flex-direction: column;
            gap: 1rem;
            border: 1px solid rgba(148, 163, 184, 0.2);
            flex: 1 1 calc(25% - 1.5rem);
            max-width: 300px;
            transition: transform 0.3s ease, box-shadow 0.3s ease;
        }}

        .feature-card:hover {{
            transform: translateY(-10px);
            box-shadow: 0 16px 40px rgba(15, 23, 42, 0.2);
        }}

        .feature-card img {{
            width: 100%;
            border-radius: 12px;
            object-fit: cover;
            height: 190px;
        }}

        .feature-card h3 {{
            margin: 0;
            font-size: 1.25rem;
            color: #0f172a;
        }}

        .feature-card p {{
            margin: 0;
            color: #475569;
            line-height: 1.6;
            font-size: 0.98rem;
        }}

        .advantages-grid {{
            display: flex;
            flex-wrap: wrap;
            gap: 1.5rem;
            margin-bottom: 2rem;
            justify-content: center;
        }}

        .advantage-1 {{
            background: #e3f2fd;
            border-left: 5px solid #2196f3;
        }}

        .advantage-2 {{
            background: #e8f5e9;
            border-left: 5px solid #4caf50;
        }}

        .advantage-3 {{
            background: #fff3e0;
            border-left: 5px solid #ff9800;
        }}

        .advantage-4 {{
            background: #fce4ec;
            border-left: 5px solid #e91e63;
        }}

        .footer {{
            text-align: center;
            color: #475569;
            font-size: 0.9rem;
            margin-top: 2rem;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )

    create_menu()

    st.markdown(
        """
        <section class="hero-section animate-fade">
            <div style="position:relative;z-index:2;">
                <h1>Bienvenue sur Smart Market Analytics</h1>
                <p>Votre plateforme unifiée pour analyser vos ventes et piloter la performance retail.</p>
            </div>
        </section>
        """,
        unsafe_allow_html=True,
    )

    colonne1, colonne2 = st.columns(2)
    with colonne1:
        st.markdown("### Apropos")
        st.write(
            """**Smart Market Analytics** est une plateforme innovante conçue pour aider les entreprises à analyser leurs données de vente, 
        identifier les tendances et prendre des décisions éclairées. Grâce à des outils avancés de visualisation et d'analyse, 
        vous pouvez optimiser vos performances et opérer les choix stratégiques."""
        )

    with colonne2:
        st.markdown("### Pourquoi nous choisir ?")
        st.write(
            """
            - **Analyse approfondie** : Explorez vos données sous différents angles pour découvrir des insights cachés.
            - **Visualisations interactives** : Des tableaux de bord dynamiques pour une prise de décision rapide.
            - **Optimisation des performances** : Identifiez les opportunités d'amélioration et maximisez vos revenus.

            Rejoignez-nous pour transformer vos données en actions concrètes et piloter votre succès !"""
        )

    if not st.session_state.get("authenticated", False):
        st.info("👋 Bienvenue sur Smart Market Analytics !")

    st.markdown("## Fonctionnalités phares")
    st.markdown(
        f"""
        <section class="feature-grid animate-stagger">
            <article class="feature-card">
                <img src="{IMAGES['analytics']}" alt="Import & Analyse" loading="lazy" />
                <h3>Importation et gouvernance des données</h3>
                <p>Centralisez et nettoyez vos données pour garantir leur qualité et leur traçabilité.</p>
            </article>
            <article class="feature-card">
                <img src="{IMAGES['dashboard']}" alt="Analyse croisée" loading="lazy" />
                <h3>Analyses croisées & insights contextuels</h3>
                <p>Analysez vos performances en tenant compte des facteurs externes et segmentez vos données intelligemment.</p>
            </article>
            <article class="feature-card">
                <img src="{IMAGES['team']}" alt="Visualisations" loading="lazy" />
                <h3>Visualisation décisionnelle & reporting</h3>
                <p>Créez des tableaux de bord interactifs pour suivre vos KPIs en temps réel et partager des rapports personnalisés.</p>
            </article>
            <article class="feature-card">
                <img src="{IMAGES['insights']}" alt="Prédictions" loading="lazy" />
                <h3>Prédictions et planification</h3>
                <p>Anticipez les tendances futures grâce à des modèles avancés et optimisez vos décisions.</p>
            </article>
        </section>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("## Avantages différenciants")
    st.markdown(
        """
        <section class="advantages-grid animate-stagger">
            <article class="feature-card advantage-1">
                <h3>Diagnostic 360° des performances</h3>
                <p>Consolidez vos KPIs ventes, marge et stock pour identifier rapidement les leviers de croissance.</p>
            </article>
            <article class="feature-card advantage-2">
                <h3>Segmentation dynamique</h3>
                <p>Analysez vos données par zone, magasin, catégorie ou période pour détecter les opportunités locales.</p>
            </article>
            <article class="feature-card advantage-3">
                <h3>Qualité et gouvernance des données</h3>
                <p>Assurez-vous de la fiabilité de vos analyses grâce aux contrôles, historiques d’import et alertes qualité.</p>
            </article>
            <article class="feature-card advantage-4">
                <h3>Diffusion simplifiée des insights</h3>
                <p>Partagez des tableaux de bord prêts à l’emploi et synchrones pour éclairer vos comités de décision.</p>
            </article>
        </section>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("---")
    if st.session_state.get("authenticated", False):
        user_text = st.session_state.get("username", "")
    else:
        user_text = "Visiteur (connectez-vous pour accéder à toutes les fonctionnalités)"
    st.markdown(
        f"<div class='footer'>© 2025 Smart Market Analytics · {user_text}</div>",
        unsafe_allow_html=True,
    )

def render_dashboard_page():
    hero_img = IMAGES["dashboard_hero"]
    st.markdown(
        f"""
        <style>
        :root {{
            --dashboard-hero-img: url('{hero_img}');
        }}
        .dashboard-hero {{
            position: relative;
            margin: -2.5rem -2.5rem 2rem -2.5rem;
            padding: 4rem 2rem;
            border-radius: 0 0 28px 28px;
            color: white;
            backdrop-filter: blur(8px);
            text-align: center;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            min-height: 240px;
            background: linear-gradient(135deg, rgba(99, 102, 241, 0.75), rgba(15, 23, 42, 0.92)),
                        var(--dashboard-hero-img);
            background-size: cover;
            background-position: center;
            box-shadow: 0 22px 50px rgba(15, 23, 42, 0.35);
        }}
        .dashboard-hero h1 {{
            font-size: clamp(2.2rem, 4vw, 3.2rem);
            margin: 0 0 1rem 0;
            font-weight: 700;
            text-shadow: 0 2px 4px rgba(0,0,0,0.2);
            max-width: 1000px;
        }}
        .dashboard-hero p {{
            font-size: clamp(1.1rem, 2vw, 1.3rem);
            max-width: 800px;
            opacity: 0.95;
            line-height: 1.6;
            margin: 0 auto 1.5rem;
            text-shadow: 0 1px 3px rgba(0,0,0,0.2);
        }}
        .dashboard-hero__meta {{
            display: flex;
            flex-wrap: wrap;
            gap: 1rem;
            margin-top: 1.5rem;
        }}
        .dashboard-hero__tag {{
            background: rgba(255, 255, 255, 0.16);
            border-radius: 999px;
            padding: 0.55rem 1.25rem;
            font-size: 0.95rem;
            letter-spacing: 0.02em;
            box-shadow: inset 0 0 0 1px rgba(255,255,255,0.18);
        }}
        .kpi-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 1.4rem;
            margin: 1.8rem 0 2.2rem;
        }}
        .kpi-card {{
            position: relative;
            padding: 1.8rem;
            border-radius: 18px;
            color: #fff;
            overflow: hidden;
            box-shadow: 0 20px 45px rgba(15, 23, 42, 0.25);
        }}
        .kpi-card::after {{
            content: "";
            position: absolute;
            inset: 0;
            background: linear-gradient(135deg, rgba(255,255,255,0.15), transparent 55%);
            pointer-events: none;
        }}
        .kpi-card__label {{
            font-size: 0.95rem;
            letter-spacing: 0.04em;
            text-transform: uppercase;
            opacity: 0.85;
        }}
        .kpi-card__value {{
            font-size: 2rem;
            font-weight: 700;
            margin: 0.35rem 0 0.6rem;
        }}
        .kpi-card__caption {{
            margin: 0;
            font-size: 0.95rem;
            opacity: 0.9;
        }}
        .kpi-card--indigo {{ background: linear-gradient(135deg, #4f46e5, #312e81); }}
        .kpi-card--emerald {{ background: linear-gradient(135deg, #10b981, #047857); }}
        .kpi-card--amber {{ background: linear-gradient(135deg, #f59e0b, #b45309); }}
        .kpi-card--rose {{ background: linear-gradient(135deg, #ec4899, #9d174d); }}
        .kpi-card--sky {{ background: linear-gradient(135deg, #0ea5e9, #1e3a8a); }}
        .kpi-card--slate {{ background: linear-gradient(135deg, #475569, #111827); }}
        @media (max-width: 992px) {{
            .dashboard-hero {{
                margin: -1.5rem -1.5rem 1.5rem -1.5rem;
                padding: 3rem 1.8rem;
                border-radius: 0 0 22px 22px;
            }}
        }}
        @media (max-width: 640px) {{
            .dashboard-hero {{
                margin: -1rem -1rem 1rem -1rem;
                padding: 2.5rem 1.4rem;
            }}
        }}
        </style>
        <section class="dashboard-hero animate-fade">
            <h1>Vue d'ensemble des performances de vos ventes.</h1>
            <p>Suivez les revenus, unités vendues et tendances clés en un coup d'œil. Identifiez vos opportunités en temps réel grâce à nos indicateurs intelligents.</p>
            <div class="dashboard-hero__meta animate-stagger">
                <span class="dashboard-hero__tag">📈 KPIs en temps réel</span>
                <span class="dashboard-hero__tag">🔎 Insights automatiques</span>
                <span class="dashboard-hero__tag">📥 Exports rapides</span>
            </div>
        </section>
        """,
        unsafe_allow_html=True,
    )

    st.subheader("📈 Dashboard Ventes — Vue professionnelle")

    if not check_data():
        return

    raw = st.session_state["data"]
    detected = detect_sales_columns(raw)
    df = detected["df"]
    date_col = detected["date_col"]
    revenue_col = detected["revenue_col"]
    qty_col = detected["qty_col"]
    product_col = detected["product_col"]
    store_col = detected["store_col"]
    order_col = detected["order_col"]
    customer_col = detected["customer_col"]

    st.sidebar.header("Paramètres affichage")
    top_n = st.sidebar.number_input("Top N (produits/magasins)", min_value=3, max_value=50, value=10, step=1)
    granularity = st.sidebar.selectbox(
        "Granularité temporelle",
        ["D", "W", "M"],
        index=0,
        format_func=lambda x: {"D": "Quotidien", "W": "Hebdo", "M": "Mensuel"}[x],
    )
    currency_label = st.sidebar.text_input("Symbole devise (optionnel)", value="€")

    n_rows, n_cols = df.shape
    global_missing_pct = round(df.isna().sum().sum() / (max(1, n_rows * n_cols)) * 100, 2)
    duplicates = int(df.duplicated().sum())

    total_revenue = None
    if revenue_col:
        total_revenue = round(pd.to_numeric(df[revenue_col], errors="coerce").sum(skipna=True))
    total_units = None
    if qty_col:
        total_units = int(pd.to_numeric(df[qty_col], errors="coerce").sum(skipna=True))
    unique_orders = int(df[order_col].nunique(dropna=True)) if order_col else None
    unique_customers = int(df[customer_col].nunique(dropna=True)) if customer_col else None
    approx_orders = unique_orders if unique_orders is not None and unique_orders > 0 else max(1, n_rows)

    avg_order_value = (
        round((total_revenue / approx_orders)) if (total_revenue is not None and approx_orders) else None
    )

    if date_col and revenue_col:
        ts = compute_time_series(df, date_col, revenue_col, freq=granularity)
        if not ts.empty:
            latest_date = ts["date"].max()
            window = timedelta(days=7) if granularity == "D" else timedelta(days=28) if granularity == "W" else timedelta(days=90)
            end = latest_date
            start = end - window
            prev_start = start - (end - start)
            prev_end = start - pd.Timedelta(days=1)

            recent_sum = round(ts[(ts["date"] > start) & (ts["date"] <= end)][revenue_col].sum())
            prev_sum = round(ts[(ts["date"] > prev_start) & (ts["date"] <= prev_end)][revenue_col].sum())
            pct_change = None
            if prev_sum != 0:
                pct_change = round((recent_sum - prev_sum) / abs(prev_sum) * 100, 1)
        else:
            recent_sum = prev_sum = pct_change = None
    else:
        ts = pd.DataFrame()
        recent_sum = prev_sum = pct_change = None

    st.subheader("🎯 KPIs essentiels")
    kpi_cards = [
        {
            "title": "Revenu total",
            "value": fmt_currency(total_revenue, currency_label) if total_revenue is not None else "N/A",
            "caption": "Somme sur la période filtrée",
            "tone": "indigo",
        },
        {
            "title": "Unités vendues",
            "value": fmt_number(total_units),
            "caption": "Quantités agrégées",
            "tone": "emerald",
        },
        {
            "title": "Commandes uniques",
            "value": fmt_number(unique_orders if unique_orders is not None else n_rows),
            "caption": "Transactions distinguées",
            "tone": "sky",
        },
        {
            "title": "Clients uniques",
            "value": fmt_number(unique_customers),
            "caption": "Clients identifiés",
            "tone": "rose",
        },
        {
            "title": "Taux de données manquantes",
            "value": f"{round(global_missing_pct)} %",
            "caption": "Sur l'ensemble des colonnes",
            "tone": "amber",
        },
        {
            "title": "Lignes dupliquées",
            "value": fmt_number(duplicates),
            "caption": "À investiguer pour qualité",
            "tone": "slate",
        },
    ]

    if avg_order_value:
        kpi_cards.append(
            {
                "title": "Panier moyen",
                "value": fmt_currency(avg_order_value, currency_label),
                "caption": "Valeur moyenne par commande",
                "tone": "emerald",
            }
        )

    if recent_sum is not None and prev_sum is not None:
        variation = f"{pct_change:+.1f}%" if pct_change is not None else "N/A"
        kpi_cards.append(
            {
                "title": "Revenu récent",
                "value": fmt_currency(recent_sum, currency_label),
                "caption": f"vs période précédente : {variation}",
                "tone": "indigo",
            }
        )

    cards_html = "".join(
        f"""
        <article class="kpi-card kpi-card--{card['tone']} animate-slide-up">
            <span class="kpi-card__label">{card['title']}</span>
            <h3 class="kpi-card__value">{card['value']}</h3>
            {f"<p class='kpi-card__caption'>{card['caption']}</p>" if card.get('caption') else ''}
        </article>
        """
        for card in kpi_cards
    )

    st.markdown(f"<section class='kpi-grid'>{cards_html}</section>", unsafe_allow_html=True)

    st.subheader("📈 Évolution temporelle")
    if not ts.empty:
        line_fig = px.line(ts, x="date", y=revenue_col, title="Revenu — série temporelle", markers=False)
        line_fig.update_traces(line=dict(color="#1f77b4"))
        line_fig.update_layout(margin=dict(t=40, l=10, r=10, b=10), height=360)
        st.plotly_chart(line_fig, use_container_width=True)
    else:
        st.info("Pas assez d'informations date+revenue pour tracer la série temporelle.")

    st.subheader("🏆 Top éléments")
    tp_col, ts_col = st.columns(2)
    if product_col:
        with tp_col:
            st.markdown("**Top produits**")
            if revenue_col:
                top_products = (
                    df.groupby(product_col)[revenue_col].sum().sort_values(ascending=False).head(top_n)
                )
                fig = px.bar(
                    top_products.reset_index(),
                    x=product_col,
                    y=revenue_col,
                    title=f"Top {top_n} produits par revenu",
                )
            elif qty_col:
                top_products = df.groupby(product_col)[qty_col].sum().sort_values(ascending=False).head(top_n)
                fig = px.bar(
                    top_products.reset_index(),
                    x=product_col,
                    y=qty_col,
                    title=f"Top {top_n} produits par unités",
                )
            else:
                top_products = df[product_col].value_counts().head(top_n)
                fig = px.bar(
                    top_products.reset_index(),
                    x=product_col,
                    y=top_products.name,
                    title=f"Top {top_n} produits (occurrences)",
                )
            fig.update_layout(height=380, margin=dict(t=40, l=10, r=10, b=10))
            st.plotly_chart(fig, use_container_width=True)
    else:
        tp_col.info("Aucune colonne produit détectée")

    if store_col:
        with ts_col:
            st.markdown("**Top magasins**")
            if revenue_col:
                top_stores = (
                    df.groupby(store_col)[revenue_col].sum().sort_values(ascending=False).head(top_n)
                )
                fig2 = px.bar(
                    top_stores.reset_index(),
                    x=store_col,
                    y=revenue_col,
                    title=f"Top {top_n} magasins par revenu",
                )
            elif qty_col:
                top_stores = df.groupby(store_col)[qty_col].sum().sort_values(ascending=False).head(top_n)
                fig2 = px.bar(
                    top_stores.reset_index(),
                    x=store_col,
                    y=qty_col,
                    title=f"Top {top_n} magasins par unités",
                )
            else:
                top_stores = df[store_col].value_counts().head(top_n)
                fig2 = px.bar(
                    top_stores.reset_index(),
                    x=store_col,
                    y=top_stores.name,
                    title=f"Top {top_n} magasins (occ.)",
                )
            fig2.update_layout(height=380, margin=dict(t=40, l=10, r=10, b=10))
            st.plotly_chart(fig2, use_container_width=True)
    else:
        ts_col.info("Aucune colonne magasin détectée")

    st.subheader("🔎 Alertes & insights automatiques")
    alerts = []
    if global_missing_pct > 20:
        alerts.append(f"⚠️ Taux de valeurs manquantes élevé: {global_missing_pct}%")
    if duplicates > 0:
        alerts.append(f"⚠️ {duplicates} lignes dupliquées détectées")
    if revenue_col and ts.shape[0] > 0:
        peak = ts.loc[ts[revenue_col].idxmax()]
        trough = ts.loc[ts[revenue_col].idxmin()]
        alerts.append(f"📌 Meilleure date: {peak['date'].date()} ({fmt_currency(peak[revenue_col], currency_label)})")
        alerts.append(f"📌 Pire date: {trough['date'].date()} ({fmt_currency(trough[revenue_col], currency_label)})")
    if alerts:
        for alert in alerts:
            st.info(alert)
    else:
        st.success("✅ Aucune alerte majeure détectée")

    st.subheader("📋 Résumé rapide — colonnes clés détectées")
    cols_summary = []
    if revenue_col:
        cols_summary.append({"Attribut": "Colonne Revenu", "Valeur": revenue_col})
    if qty_col:
        cols_summary.append({"Attribut": "Colonne Quantité", "Valeur": qty_col})
    if date_col:
        cols_summary.append({"Attribut": "Colonne Date", "Valeur": date_col})
    if product_col:
        cols_summary.append({"Attribut": "Colonne Produit", "Valeur": product_col})
    if store_col:
        cols_summary.append({"Attribut": "Colonne Magasin", "Valeur": store_col})
    if order_col:
        cols_summary.append({"Attribut": "Colonne Commande", "Valeur": order_col})
    if customer_col:
        cols_summary.append({"Attribut": "Colonne Client", "Valeur": customer_col})
    st.table(pd.DataFrame(cols_summary))

    st.subheader("⬇️ Export rapide")
    export_cols = [c for c in [date_col, product_col, store_col, order_col, customer_col, revenue_col, qty_col] if c]
    if export_cols:
        tmp_export = df[export_cols].copy()
        tmp_csv = tmp_export.to_csv(index=False).encode("utf-8")
        st.download_button("Télécharger extrait CSV (colonnes clés)", tmp_csv, "sales_extract.csv", "text/csv")
    else:
        st.info("Aucune colonne clé détectée pour export")

    with st.expander("🔍 Explorer les données brutes (filtrer)"):
        rows = st.slider("Lignes à afficher", 5, 500, 50)
        sel_cols = st.multiselect(
            "Colonnes",
            df.columns.tolist(),
            default=export_cols[:10] if export_cols else df.columns.tolist()[:10],
        )
        view = df[sel_cols].head(rows)
        st.dataframe(view)


def render_analytics_page():
    st.subheader("Analyses avancées")
    st.image(
        IMAGES["analytics"],
        use_container_width=True,
        caption="Vos analyses personnalisées s'afficheront ici",
    )
    st.warning(
        "📂 Les visualisations analytiques seront générées à partir des jeux de données téléversés. Importez vos fichiers pour activer les filtres et insights contextuels."
    )
    st.markdown(
        """
        ### Étapes recommandées
        1. Téléversez un dataset structuré (ventes, stocks, campagnes…).
        2. Déclarez les dimensions clés (produit, zone, canal, période) pour la segmentation.
        3. Configurez vos indicateurs calculés (marge, panier moyen, taux de conversion, etc.).
        4. Activez les scénarios IA/prédictifs selon vos besoins métier.
        """
    )


def render_upload_page():
    theme = st.session_state.get("theme", "light")
    step_text = "#0b1324"
    step_bg = "rgba(15, 23, 42, 0.05)"
    step_border = "rgba(15, 23, 42, 0.12)"
    highlight_bg = "rgba(79, 70, 229, 0.2)"
    highlight_border = "rgba(129, 140, 248, 0.7)"
    highlight_text = "#11123a"
    highlight_bg_2 = "rgba(3, 105, 161, 0.18)"
    highlight_border_2 = "rgba(56, 189, 248, 0.75)"
    highlight_text_2 = "#082f49"
    highlight_bg_3 = "rgba(15, 118, 110, 0.2)"
    highlight_border_3 = "rgba(94, 234, 212, 0.75)"
    highlight_text_3 = "#052e2b"

    st.markdown(
        f"""
        <style>
        .upload-hero {{
            position: relative;
            margin: -2.5rem -2.5rem 2rem -2.5rem;
            padding: 4rem 2rem;
            border-radius: 0 0 28px 28px;
            color: white;
            background: linear-gradient(135deg, rgba(14, 165, 233, 0.8), rgba(15, 23, 42, 0.9)),
                        url('{IMAGES['upload']}');
            background-size: cover;
            background-position: center;
            text-align: center;
            box-shadow: 0 20px 40px rgba(15, 23, 42, 0.35);
        }}
        .upload-hero h1 {{
            font-size: clamp(2rem, 3.4vw, 3rem);
            margin-bottom: 0.8rem;
        }}
        .upload-hero p {{
            max-width: 800px;
            margin: 0 auto;
            font-size: 1.1rem;
            opacity: 0.95;
        }}
        .upload-process {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
            gap: 1.25rem;
            margin-top: 1.25rem;
        }}
        .upload-process article,
        .step-card {{
            position: relative;
            background: rgba(255,255,255,0.95);
            border-radius: 16px;
            padding: 1.35rem 1.2rem 1.2rem 1.2rem;
            border: 1px solid rgba(15, 23, 42, 0.06);
            box-shadow: 0 14px 32px rgba(15,23,42,0.08);
            transition: transform 0.25s ease, box-shadow 0.25s ease;
            min-height: 220px;
            display: flex;
            flex-direction: column;
            justify-content: flex-start;
        }}
        .upload-process article:hover,
        .step-card:hover {{
            transform: translateY(-6px);
            box-shadow: 0 22px 50px rgba(15,23,42,0.15);
        }}
        .upload-process h4,
        .step-card h4 {{
            margin: 0 0 0.4rem 0;
            color: #0f172a;
        }}
        .upload-process p,
        .step-card p {{
            margin: 0;
            color: #475569;
        }}
        .upload-steps-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
            gap: 1.25rem;
            margin-top: 1.25rem;
        }}
        .step-card .step-pill {{
            width: 42px;
            height: 42px;
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 700;
            color: white;
            margin-bottom: 0.9rem;
            box-shadow: 0 10px 25px rgba(15,23,42,0.15);
        }}
        .step-card h4 {{
            margin: 0 0 0.4rem 0;
            color: #0f172a;
        }}
        .step-card p {{
            margin: 0;
            color: #475569;
        }}
        .step-1 {{
            border-color: {highlight_border};
        }}
        .step-1 .step-pill {{
            background: linear-gradient(135deg, rgba(79, 70, 229, 1), rgba(129, 140, 248, 1));
        }}
        .step-2 {{
            border-color: {highlight_border_2};
        }}
        .step-2 .step-pill {{
            background: linear-gradient(135deg, rgba(3, 105, 161, 1), rgba(56, 189, 248, 1));
        }}
        .step-3 {{
            border-color: {highlight_border_3};
        }}
        .step-3 .step-pill {{
            background: linear-gradient(135deg, rgba(15, 118, 110, 1), rgba(94, 234, 212, 1));
        }}
        </style>
        <section class="upload-hero animate-fade">
            <h1>📤 Téléversement sécurisé</h1>
            <p>Ajoutez vos fichiers CSV/Excel : nous assurons le contrôle qualité, la normalisation et l’historisation avant de nourrir vos dashboards.</p>
        </section>
        """,
        unsafe_allow_html=True,
    )

    col1, _ = st.columns([1.2, 1])
    with col1:
        st.markdown("### Déposez vos fichiers")
        uploaded_file = st.file_uploader(
            "Fichier CSV ou Excel",
            type=["csv", "xlsx"],
            help=f"Formats pris en charge : .csv, .xlsx (UTF-8). Taille max {MAX_UPLOAD_MB} Mo."
        )
        if uploaded_file:
            file_size = uploaded_file.size or len(uploaded_file.getbuffer())
            if file_size > MAX_UPLOAD_BYTES:
                st.error(
                    f"❌ {uploaded_file.name} dépasse la limite de 1 Go (taille détectée : {file_size / (1024**2):.1f} Mo). Veuillez compresser ou segmenter le fichier."
                )
                uploaded_file = None
            else:
                st.success(
                    f"✅ {uploaded_file.name} a été reçu. Vous recevrez une notification dès que le dataset sera disponible dans vos analyses."
                )

    step_col, reason_col = st.columns(2)
    with step_col:
        st.markdown("#### Étapes de traitement")
        st.markdown(
            """
            <section class="upload-steps-grid">
                <article class="step-card step-1">
                    <div class="step-pill">1</div>
                    <h4>Validation du schéma</h4>
                    <p>Contrôle du format, des doublons et alignement sur vos référentiels internes.</p>
                </article>
                <article class="step-card step-2">
                    <div class="step-pill">2</div>
                    <h4>Nettoyage automatique</h4>
                    <p>Types, valeurs manquantes et normalisation des colonnes critiques.</p>
                </article>
                <article class="step-card step-3">
                    <div class="step-pill">3</div>
                    <h4>Historisation & mise à disposition</h4>
                    <p>Versionning sécurisé puis propagation des datasets aux dashboards.</p>
                </article>
            </section>
            """,
            unsafe_allow_html=True,
        )
    with reason_col:
        st.markdown("### Pourquoi un upload gouverné ?")
        st.markdown(
            """
            <section class="upload-process">
                <article>
                    <h4>🔐 Traçabilité</h4>
                    <p>Chaque import est journalisé avec horodatage et propriétaire.</p>
                </article>
                <article>
                    <h4>🧼 Qualité</h4>
                    <p>Contrôles auto sur formats, cohérence des clés et valeurs aberrantes.</p>
                </article>
                <article>
                    <h4>⚙️ Normalisation</h4>
                    <p>Uniformisation des colonnes (dates, codes magasin, devise…).</p>
                </article>
            </section>
            """,
            unsafe_allow_html=True,
        )


def render_prediction_page():
    st.subheader("Prévisions de la demande")
    col1, col2 = st.columns([1.3, 1])
    with col1:
        with st.form("prediction_form"):
            horizon = st.select_slider("Horizon", options=["1 semaine", "1 mois", "3 mois"])
            scenario = st.selectbox("Scénario", ["Tendance actuelle", "Campagne marketing", "Nouveau produit"])
            budget = st.slider("Budget marketing", min_value=10_000, max_value=150_000, step=5_000, format="%d €")
            submitted = st.form_submit_button("Lancer la simulation")
        if submitted:
            st.info(
                f"Projection {horizon.lower()} sous scénario '{scenario}' : croissance estimée +{3 + budget / 100_000:.1f}% vs tendance."
            )
    with col2:
        st.image(
            IMAGES["prediction"],
            use_container_width=True,
            caption="Modélisation avancée des ventes",
        )
        st.caption("Comparez plusieurs scénarios pour dimensionner stocks et campagnes media.")


def render_authenticated_area():
    st.sidebar.title("Menu de navigation")
    st.sidebar.write(f"👤 Connecté avec : **{st.session_state.user_email}**")
    page = st.sidebar.radio(
        "Aller à :",
        ["Accueil", "Dashboard", "Analytics", "Téléversement de fichiers", "Prédiction"],
    )

    if page == "Téléversement de fichiers":
        st.title("")
    else:
        st.title(page)
    renderers = {
        "Accueil": render_home_page,
        "Dashboard": render_dashboard_page,
        "Analytics": render_analytics_page,
        "Téléversement de fichiers": render_upload_page,
        "Prédiction": render_prediction_page,
    }
    renderers.get(page, render_home_page)()

    if st.sidebar.button("Se déconnecter"):
        st.session_state.is_authenticated = False
        st.session_state.user_email = ""
        st.experimental_set_query_params()


def render_auth_forms():
    st.title("Bienvenue sur Smart Market Analytics")
    st.subheader("Connexion")

    col1, col2 = st.columns(2)

    with col1:
        st.header("Connexion")
        with st.form("info_connexion"):
            email = st.text_input("Adresse e-mail")
            password = st.text_input("Mot de passe", type="password")
            submit = st.form_submit_button("Se connecter")

            if submit:
                if not email or not password:
                    st.error("Veuillez remplir tous les champs.")
                else:
                    user_email = verify_credentials(email, password)
                    if user_email:
                        st.session_state.is_authenticated = True
                        st.session_state.user_email = user_email
                        st.success(f"Connexion réussie !")
                        st.experimental_set_query_params(authenticated="true")
                    else:
                        st.error("Adresse e-mail ou mot de passe incorrect.")

    with col2:
        st.header("Inscription")
        with st.form("form_inscription"):
            new_email = st.text_input("Adresse e-mail", key="register_email")
            new_password = st.text_input("Mot de passe", type="password", key="register_password")
            confirm_password = st.text_input("Confirmez le mot de passe", type="password")
            register = st.form_submit_button("S'inscrire")

            if register:
                if not all([new_email, new_password, confirm_password]):
                    st.error("Veuillez remplir tous les champs.")
                elif new_password != confirm_password:
                    st.error("Les mots de passe ne correspondent pas.")
                elif register_user(new_email, new_password):
                    st.success("Inscription réussie ! Vous pouvez maintenant vous connecter.")


def main():
    st.set_page_config(page_title="Connexion", page_icon="📊", layout="wide")
    st.session_state.setdefault("is_authenticated", False)
    st.session_state.setdefault("user_email", "")

    if st.session_state.is_authenticated:
        render_authenticated_area()
    else:
        render_auth_forms()


if __name__ == "__main__":
    main()
