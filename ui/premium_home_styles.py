"""Presentation-only Home editorial target. No financial or authority inputs."""

PREMIUM_HOME_CSS = r"""
.atlas-editorial-brief.atlas-daily-brief{display:block;padding:clamp(1.1rem,3vw,2.4rem);background:radial-gradient(ellipse at 100% 0%,#143c49 0%,#101f32 46%,#101927 100%);border:1px solid #294253;border-radius:22px;box-shadow:0 18px 60px #0002}
.atlas-editorial-brief header{max-width:920px;margin-bottom:1.6rem}
.atlas-editorial-brief header small,.atlas-home-section-kicker{color:#76dfcd;font-size:.72rem;font-weight:750;letter-spacing:.13em}
.atlas-editorial-brief h1{font-size:clamp(2rem,4.2vw,3.6rem)!important;letter-spacing:-.045em;line-height:1.08!important;margin:.55rem 0!important;color:#f1f6fc}
.atlas-editorial-brief .atlas-editorial-subtitle{font-size:1.08rem;color:#b5c9df;margin:.5rem 0!important}
.atlas-editorial-columns{display:grid;grid-template-columns:1fr 1fr;gap:2rem}
.atlas-editorial-columns article{border-top:1px solid #385164;padding-top:1rem;min-width:0}
.atlas-editorial-columns small{color:#8fa9c1;font-size:.68rem;letter-spacing:.08em;font-weight:750}
.atlas-editorial-columns p{font-size:.96rem!important;line-height:1.65!important;color:#d4dfec}
.atlas-editorial-brief footer{border-top:1px solid #294253;padding-top:.85rem;margin-top:1rem;font-size:.73rem!important;line-height:1.55;color:#9eb0c4}
.atlas-home-market-strip{margin:.7rem 0 1rem!important;padding:.75rem 1rem!important;border:1px solid #253449;border-radius:12px!important;display:flex!important;justify-content:space-between;gap:1rem;flex-wrap:wrap}
.atlas-home-market-strip p{margin:0!important;font-variant-numeric:tabular-nums}
.atlas-home-section-kicker{margin:1.1rem 0 .65rem}
.atlas-home-featured-case.atlas-home-compact-card{padding:1.5rem;border:1px solid #36525a;border-left:4px solid #60d7c2;background:linear-gradient(115deg,#152a38,#111c2b);border-radius:18px}
.atlas-home-featured-case h3{font-size:1.65rem!important;letter-spacing:-.025em}
.atlas-home-featured-case .atlas-home-compact-values{grid-template-columns:repeat(3,minmax(0,1fr));gap:.75rem;margin:1.2rem 0}
.atlas-home-featured-case .atlas-home-compact-values span{padding:.75rem .9rem;background:#0b1525;border:1px solid #26394b;border-radius:10px}
.atlas-home-featured-case .atlas-home-compact-values b{font-size:1.35rem;color:#eef5ff;font-variant-numeric:tabular-nums;letter-spacing:-.02em}
.atlas-home-featured-case .atlas-home-compact-values small{font-size:.73rem;color:#9dafc3;margin-bottom:.25rem}
.atlas-home-featured-case p{max-width:850px;font-size:.94rem!important;line-height:1.6!important}
.atlas-home-compact-card:not(.atlas-home-featured-case){padding:1rem;border:1px solid #2b3b50;border-radius:16px;background:#101c2c;height:auto}
.atlas-home-compact-card footer{opacity:1!important;color:#a2b2c7!important;line-height:1.5}
@media(max-width:800px){.atlas-editorial-columns{grid-template-columns:1fr;gap:.6rem}.atlas-editorial-brief header{margin-bottom:1rem}.atlas-home-featured-case.atlas-home-compact-card{padding:1rem}.atlas-home-featured-case .atlas-home-compact-values{grid-template-columns:repeat(2,minmax(0,1fr));gap:.5rem}.atlas-home-featured-case .atlas-home-compact-values b{font-size:1.15rem}.atlas-home-featured-case h3{font-size:1.3rem!important}.atlas-home-market-strip{display:block!important}.atlas-home-market-strip p{margin-top:.4rem!important}}
div[data-testid="stElementContainer"]:has([data-atlas-qa="home-guidance-section"]),div[data-testid="stElementContainer"]:has([data-atlas-qa="home-top-ideas"]),div[data-testid="stElementContainer"]:has([data-atlas-qa="home-opportunity-spotlight"]){display:none}
@media(max-width:900px){[data-testid="stHorizontalBlock"]:has(.st-key-home_top_idea_position_2){flex-direction:column}[data-testid="stHorizontalBlock"]:has(.st-key-home_top_idea_position_2)>[data-testid="stColumn"]{width:100%!important;flex:1 1 100%!important}}
@media(prefers-reduced-motion:reduce){.atlas-editorial-brief{scroll-behavior:auto}}
"""
