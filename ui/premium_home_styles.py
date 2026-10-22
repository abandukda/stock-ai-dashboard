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

PREMIUM_HOME_CSS += r"""
.atlas-reference-command.atlas-editorial-brief{display:grid;grid-template-columns:.85fr 1.35fr;gap:1.5rem;padding:1.5rem;background:linear-gradient(125deg,#06101e,#071422 48%,#081521);border-color:#18384d;border-radius:16px}
.atlas-reference-command .atlas-reference-brand{position:relative;overflow:hidden;padding:1.1rem .7rem;min-width:0;isolation:isolate}
.atlas-reference-brand>small{font-weight:800;color:#69caff;font-size:.7rem;letter-spacing:.13em}
.atlas-reference-command h1{font-size:clamp(1.9rem,3vw,2.9rem)!important;margin:.8rem 0!important;line-height:1.08!important;letter-spacing:-.035em}
.atlas-reference-brand>p{font-size:.95rem!important;line-height:1.6!important;max-width:290px;color:#c8d7e6}
.atlas-reference-explore{display:inline-block;padding:.7rem .9rem;border:1px solid #2698fc;border-radius:8px;background:#0878eb;color:white!important;font-weight:700;text-decoration:none!important;font-size:.83rem;margin:.5rem 0}
.atlas-brand-orbit{position:absolute;z-index:-1;width:330px;height:330px;top:20px;right:-130px;border:1px solid #087bed66;border-radius:50%;background:radial-gradient(ellipse at 30% 30%,#137ad14a,#04172788 60%,#020712);box-shadow:-15px -12px 50px #0686ff22}
.atlas-reference-intelligence{min-width:0}
.atlas-reference-intelligence header{display:flex;justify-content:space-between;align-items:baseline;gap:.7rem;margin:0 0 .4rem!important;flex-wrap:wrap}
.atlas-reference-intelligence h2{font-size:1.05rem!important;margin:0!important;letter-spacing:0}
.atlas-reference-intelligence header span,.atlas-reference-source{font-size:.7rem!important;color:#91a7bd;margin:.3rem 0 .6rem!important}
.atlas-reference-indices{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:.5rem}
.atlas-reference-index{padding:.8rem .65rem;background:linear-gradient(140deg,#112438,#0a1927);border:1px solid #1d3447;border-radius:10px;min-width:0}
.atlas-reference-index small{color:#c2d4e6;font-size:.7rem;font-weight:700;display:block}.atlas-reference-index strong{font-size:clamp(.95rem,1.45vw,1.3rem);display:block;margin:.25rem 0;color:#f3f8ff;font-variant-numeric:tabular-nums}.atlas-reference-index span{font-size:.8rem;font-weight:750}.atlas-reference-index .positive{color:#38ebb0}.atlas-reference-index .negative{color:#ff9d9d}.atlas-reference-index .neutral{color:#a9bdd0}
.atlas-reference-brief{padding:.8rem 1rem;border:1px solid #17374e;border-radius:10px;background:#0b1d30;margin-top:.65rem}.atlas-reference-brief>small{font-size:.7rem;color:#6bceff;font-weight:750;letter-spacing:.06em}.atlas-reference-brief p{font-size:.85rem!important;line-height:1.6!important;margin:.4rem 0!important}.atlas-reference-brief summary{font-size:.75rem;color:#6bceff;cursor:pointer}.atlas-reference-command>footer{grid-column:1/-1;margin-top:0;font-size:.7rem!important}
.atlas-reference-shortlist{background:#0b1928;border:1px solid #23394e;border-radius:12px;padding:.8rem;margin-bottom:.6rem}.atlas-reference-shortlist h3{font-size:1rem!important;margin:0 0 .7rem!important}.atlas-reference-shortlist [role="region"]{overflow-x:auto}.atlas-reference-shortlist table{width:100%;border-collapse:collapse;font-size:.75rem;font-variant-numeric:tabular-nums}.atlas-reference-shortlist th,.atlas-reference-shortlist td{padding:.55rem .4rem!important;border-bottom:1px solid #223347;white-space:nowrap}.atlas-reference-shortlist td{text-align:right}.atlas-reference-shortlist th{text-align:left;color:#d8e5f1}.atlas-reference-shortlist thead th{font-size:.65rem;color:#91a7bd}.atlas-reference-shortlist th small{display:block;font-size:.65rem;color:#91a7bd;font-weight:400;max-width:120px;overflow:hidden;text-overflow:ellipsis}
.atlas-home-shortlist-row.atlas-home-compact-card{padding:.65rem .75rem}.atlas-home-shortlist-row .atlas-home-compact-values{gap:.2rem;margin:.4rem 0}.atlas-home-shortlist-row .atlas-home-compact-values span{padding:.25rem}.atlas-home-shortlist-row h3{font-size:1rem!important}.atlas-home-shortlist-row .atlas-home-compact-values small{font-size:.65rem}.atlas-home-shortlist-row .atlas-home-compact-values b{font-size:.8rem}.atlas-home-shortlist-row p{font-size:.76rem!important}
@media(max-width:1000px){.atlas-reference-command.atlas-editorial-brief{grid-template-columns:1fr;padding:1rem}.atlas-reference-command .atlas-reference-brand{padding:.5rem}.atlas-reference-brand>p{max-width:none}.atlas-brand-orbit{width:230px;height:230px;right:0;top:-20px}.atlas-reference-command h1{font-size:2.1rem!important}.atlas-reference-indices{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:700px){.atlas-reference-command .atlas-reference-brand{display:none}.atlas-reference-command.atlas-editorial-brief{gap:.6rem;padding:.8rem}.atlas-reference-command>footer{font-size:.66rem!important;line-height:1.4}.atlas-reference-intelligence h2{font-size:1rem!important}.atlas-reference-indices{gap:.4rem}.atlas-reference-index{padding:.65rem}.atlas-reference-shortlist{padding:.6rem}}
"""

PREMIUM_HOME_CSS += r"""
.atlas-home-shortlist-row header{display:flex;justify-content:space-between;align-items:center;gap:.5rem}.atlas-home-shortlist-row header h3{margin:0!important}.atlas-home-shortlist-row header small{font-size:.65rem;color:#75dbc5}.atlas-home-shortlist-row .atlas-home-compact-values{grid-template-columns:repeat(3,minmax(0,1fr))}.atlas-home-shortlist-row footer{font-size:.65rem!important}
.atlas-command-deck{gap:0!important;border:1px solid #24394b;border-radius:10px;margin:.2rem 0 .5rem!important}.atlas-command-deck article{padding:.45rem .65rem!important;border:0!important;border-radius:0!important;background:none!important}.atlas-command-deck b{font-size:.8rem!important}.atlas-command-deck span{font-size:.62rem!important}
@media(max-width:1000px) and (min-width:701px){.atlas-reference-command .atlas-reference-brand{min-height:0;padding:.2rem .5rem}.atlas-reference-command h1{font-size:1.65rem!important}.atlas-reference-brand>p{margin:.3rem 0!important}.atlas-brand-orbit{width:180px;height:180px}}
@media(max-width:700px){.atlas-reference-intelligence:before{content:"ATLAS AI";display:block;color:#69caff;font-size:.75rem;font-weight:800;letter-spacing:.12em;margin-bottom:.6rem}.atlas-command-deck{grid-template-columns:1fr 1fr!important}.atlas-command-deck article{padding:.4rem .5rem!important}.atlas-command-deck b{font-size:.73rem!important}}
"""
