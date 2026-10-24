"""Load both bundled SecondBrain plugins under one synthetic Hermes profile."""
import os
from pathlib import Path


home = Path(os.environ["HERMES_HOME"])
home.mkdir(parents=True, exist_ok=True)
(home / "config.yaml").write_text(
    "plugins:\n"
    "  enabled: [secondbrain-d078-guard, secondbrain-weixin-inbox]\n"
    "approvals:\n"
    "  mode: manual\n"
    "  timeout: 240\n"
    "  cron_mode: deny\n"
    "  single_query_mode: deny\n"
    "  unattended_mode: deny\n"
    "platform_toolsets:\n"
    "  api_server: [file, skills, vision]\n",
    encoding="utf-8",
)

from hermes_cli.plugins import get_plugin_manager  # noqa: E402

manager = get_plugin_manager()
manager.discover_and_load()
for plugin_name in ("secondbrain-d078-guard", "secondbrain-weixin-inbox"):
    plugin = manager._plugins.get(plugin_name)
    assert plugin is not None and not plugin.error and not plugin.deferred, plugin_name

assert len(manager._hooks.get("pre_tool_call", [])) == 1
assert len(manager._hooks.get("post_gateway_admission", [])) == 1
assert manager._plugins["secondbrain-d078-guard"].manifest.provides_hooks == ["pre_tool_call"]
assert manager._plugins["secondbrain-weixin-inbox"].manifest.provides_hooks == ["post_gateway_admission"]
print("D078_WEIXIN_PLUGIN_COEXISTENCE_PASS")
