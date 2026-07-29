def test_home_imports_morning_brief():
    from ui.home_v104 import render_v104_home
    from ui.morning_brief import render_morning_brief

    assert callable(render_v104_home)
    assert callable(render_morning_brief)
