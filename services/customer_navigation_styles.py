"""Presentation-only navigation styles, independent of cached route/role contracts."""

def customer_mobile_navigation_css() -> str:
    """All four customer destinations fit without horizontal label clipping."""
    return '''<style>
    @media(max-width:420px){
      [data-testid="stRadio"] [role="radiogroup"]{
        display:grid!important;grid-template-columns:repeat(2,minmax(0,1fr))!important;
        gap:.3rem!important;overflow:visible!important;width:100%!important;
      }
      [data-testid="stRadio"] label{
        width:100%!important;max-width:100%!important;box-sizing:border-box!important;
        min-width:0!important;white-space:normal!important;
      }
      [data-testid="stRadio"] label p{white-space:normal!important;overflow-wrap:anywhere!important}
    }
    </style>'''
