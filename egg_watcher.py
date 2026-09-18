-- egg_watcher.lua
-- language: Lua, target: Roblox executor (Xeno / Wave / Solara / Delta)
-- *слушает чат, шлёт спавны на bot.py, анти-AFK, авто-реконнект*

-- ВАЖНО: на BotHost — https://твой-бот.bothost.ru/webhook
--         локально — http://ТВОЙ_IP:8080/webhook
local WEBHOOK_URL = "https://твой-бот.bothost.ru/webhook"
local SECRET      = "твой_WEBHOOK_SECRET"
local RARITIES    = { secret = true, divine = true, legendary = true, eternal = true }

local Players    = game:GetService("Players")
local Replicated = game:GetService("ReplicatedStorage")
local Http       = game:GetService("HttpService")
local Local      = Players.LocalPlayer

local function send(eggName, rarity, zone)
    local payload = Http:JSONEncode({
        egg_name  = eggName,
        rarity    = rarity,
        zone      = zone,
        timestamp = os.date("!%Y-%m-%dT%H:%M:%SZ"),
    })
    local req = (syn and syn.request) or (http and http.request) or http_request or request
    if not req then warn("[egg_watcher] нет HttpPost"); return end
    pcall(function()
        req({
            Url     = WEBHOOK_URL,
            Method  = "POST",
            Headers = {
                ["Content-Type"]     = "application/json",
                ["X-Webhook-Secret"] = SECRET,
            },
            Body = payload,
        })
    end)
end

local function onMessage(msg)
    local lower = msg:lower()
    local rarity, egg, zone = lower:match("a (%w+) (.+) egg spawned in (.+)")
    if not rarity or not RARITIES[rarity] then return end
    local cleanEgg  = egg:gsub("^%l", string.upper)
    local cleanZone = zone:gsub("^%l", string.upper)
    print(("[egg_watcher] %s [%s] в %s"):format(cleanEgg, rarity, cleanZone))
    send(cleanEgg, rarity, cleanZone)
end

local hooked = false
local chatEvents = Replicated:FindFirstChild("DefaultChatSystemChatEvents")
if chatEvents and chatEvents:FindFirstChild("OnMessageDoneFiltering") then
    chatEvents.OnMessageDoneFiltering.OnClientEvent:Connect(function(data)
        if data and data.Message then onMessage(data.Message) end
    end)
    hooked = true
end

if not hooked then
    local tc = game:GetService("TextChatService")
    if tc and tc.TextChannels then
        for _, ch in pairs(tc.TextChannels:GetChildren()) do
            ch.MessageReceived:Connect(function(m) if m.Text then onMessage(m.Text) end end)
        end
        hooked = true
    end
end
if not hooked then warn("[egg_watcher] не нашёл канал чата") end

task.spawn(function()
    local vu = game:GetService("VirtualUser")
    Local.Idled:Connect(function()
        vu:CaptureController()
        vu:ClickButton2(Vector2.new())
    end)
end)

Players.PlayerRemoving:Connect(function(p)
    if p == Local then
        task.wait(10)
        pcall(function() game:GetService("TeleportService"):Teleport(game.PlaceId, Local) end)
    end
end)

print("[egg_watcher] запущен")
