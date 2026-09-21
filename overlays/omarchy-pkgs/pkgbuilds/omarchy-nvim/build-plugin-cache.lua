-- Run inside the actual Neovim/LazyVim build environment. Lazy's headless
-- command can report a failed clone and still let :qa! exit with status zero.
local startup_error = vim.v.errmsg
local config = require("lazy.core.config")
local plugin_state = require("lazy.core.plugin")

-- Retain subprocess output in Lazy's task log so failed fetch/build commands
-- receive ERROR status instead of only being streamed to the terminal.
config.options.headless.process = false
require("lazy").sync({ wait = true, show = false })
plugin_state.update_state()

local failures = {}
if startup_error ~= "" then
  failures[#failures + 1] = "Neovim startup: " .. startup_error
end
if vim.v.errmsg ~= "" and vim.v.errmsg ~= startup_error then
  failures[#failures + 1] = "Neovim sync: " .. vim.v.errmsg
end
if next(config.plugins) == nil then
  failures[#failures + 1] = "Lazy resolved no plugins"
end

for name, plugin in pairs(config.plugins) do
  if not plugin._.installed then
    failures[#failures + 1] = name .. ": plugin is missing after sync"
  end
  if plugin_state.has_errors(plugin) then
    failures[#failures + 1] = name .. ": a Lazy task failed (see task output above)"
  end
  for _, task in ipairs(plugin._.tasks or {}) do
    if task:running() then
      failures[#failures + 1] = name .. ": Lazy task is still running after synchronous sync"
    end
  end
end

if #failures > 0 then
  table.sort(failures)
  error("Plugin cache build failed:\n" .. table.concat(failures, "\n"), 0)
end

io.stdout:write("Verified all ", tostring(vim.tbl_count(config.plugins)), " Lazy plugins are installed without failed tasks.\n")
