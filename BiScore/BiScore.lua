BiScore = BiScore or {}
BiScoreData = BiScoreData or {}

local addon = BiScore
addon.frame = CreateFrame("Frame", "BiScoreFrame")

local function printMsg(msg)
    DEFAULT_CHAT_FRAME:AddMessage("|cff33ff99BiScore|r: " .. tostring(msg))
end

addon.Print = printMsg

local function onAddonLoaded(addonName)
    if addonName ~= "BiScore" then
        return
    end

    BiScoreDB = BiScoreDB or {}
    BiScoreCharDB = BiScoreCharDB or {}
    BiScoreCharDB.phase = BiScoreCharDB.phase or 1
    BiScoreCharDB.debug = BiScoreCharDB.debug or false

    addon:InitPhase()
    addon:InitScoring()
    addon:InitInspectQueue()
    addon:InitTooltip()
    addon:InitCharacterFrame()
    addon:InitInspectFrame()
    addon:RefreshCharacterScore()
end

local function onPlayerLogin()
    addon:RefreshCharacterScore()
end

addon.frame:SetScript("OnEvent", function(_, event, ...)
    if event == "ADDON_LOADED" then
        onAddonLoaded(...)
    elseif event == "PLAYER_LOGIN" then
        onPlayerLogin(...)
    elseif event == "INSPECT_READY" then
        addon:OnInspectReady(...)
    end
end)

addon.frame:RegisterEvent("ADDON_LOADED")
addon.frame:RegisterEvent("PLAYER_LOGIN")
addon.frame:RegisterEvent("INSPECT_READY")

SLASH_BISCORE1 = "/biscore"
SlashCmdList["BISCORE"] = function(msg)
    local args = {}
    for token in string.gmatch(msg or "", "%S+") do
        table.insert(args, token)
    end
    local cmd = string.lower(args[1] or "")

    if cmd == "phase" then
        addon:HandlePhaseSlash(args[2])
        addon:RefreshCharacterScore()
    elseif cmd == "profile" then
        addon:HandleProfileSlash(args[2])
        addon:RefreshCharacterScore()
    elseif cmd == "score" then
        local result = addon:GetUnitBiScore("player")
        if result then
            printMsg(string.format("BiScore: %d / %d (%.1f%%)", result.score, result.maxScore, result.percent * 100))
        else
            printMsg("Unable to calculate score.")
        end
    elseif cmd == "debug" then
        BiScoreCharDB.debug = not BiScoreCharDB.debug
        printMsg("Debug mode " .. (BiScoreCharDB.debug and "enabled" or "disabled"))
    else
        printMsg("Commands:")
        printMsg("/biscore phase <1-5>")
        printMsg("/biscore profile <name|auto>")
        printMsg("/biscore score")
        printMsg("/biscore debug")
    end
end
