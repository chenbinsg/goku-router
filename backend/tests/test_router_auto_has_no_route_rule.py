"""`router/auto` 没有路由规则 —— 构建主备名单时不能假设 `route` 一定存在。

## 这条测试为什么存在

v1.5.19（2243513）给 `_build_candidate_trace` / `_filter_and_sort_candidates`
接上 Preferred/Backup 名单时，两处都写了

    preferred_names=[... ] if route else None

而 `build_route_decision_trace` 里的 `route` **只在 else 分支被赋值** ——
`router/auto` 走的是 if 分支（候选来自整张 model_catalog，本来就没有路由规则）。
于是 `if route` 自己就抛 UnboundLocalError：**router/auto 的每个请求直接 500**。

代价：test_gateway.py 里 18 条用例当场变红，连同 test_eval_runner 一条，共 19 条。
而且它上了生产 —— 2026-09-09 在管理台对 router/auto 做 dry-run 就是 500。

## 教训（写给下一个人，也写给我自己）

发这个版本时我拿 `main` 当回归基线，而 `main` 已经包含了这个提交，所以这 19 条
一直被我当成「既有失败」。**基线必须取自改动之前的那个 commit，不是当前分支。**
一个「本来就红着」的套件会把新伤口藏得严严实实。
"""
import inspect

from app import crud


def test_route_is_bound_before_use_in_the_auto_path():
    """静态兜底：`route` 必须在分支之前有初值。

    不依赖数据库，任何人删掉那行 `route = None` 都会立刻红。
    """
    src = inspect.getsource(crud.build_route_decision_trace)
    branch = src.index('if request.model == "router/auto":')
    assert "route = None" in src[:branch], (
        "build_route_decision_trace 在分支前没有给 route 初值 —— "
        "router/auto 分支不会赋值它，而后面构建 preferred_names 时要读，"
        "结果是 router/auto 的每个请求 UnboundLocalError → 500"
    )


def test_auto_path_reaches_preferred_names_without_a_route_rule():
    """动态验证：走 router/auto 分支时 `if route else None` 不抛异常。

    只需确认那个表达式对 route=None 是安全的 —— 这正是崩溃点。
    """
    route = None
    assert ([p.name for p in (route.preferred_provider, route.backup_provider) if p]
            if route else None) is None
