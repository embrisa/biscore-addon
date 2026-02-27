local addon = BiScore

local SLOT_WEIGHTS = {
    [1] = 1.0,  -- Head
    [2] = 0.7,  -- Neck
    [3] = 0.9,  -- Shoulder
    [5] = 1.3,  -- Chest
    [6] = 0.8,  -- Waist
    [7] = 1.1,  -- Legs
    [8] = 0.9,  -- Feet
    [9] = 0.8,  -- Wrist
    [10] = 1.0, -- Hands
    [11] = 0.9, -- Finger 1
    [12] = 0.9, -- Finger 2
    [13] = 1.1, -- Trinket 1
    [14] = 1.1, -- Trinket 2
    [15] = 0.8, -- Back
    [16] = 1.2, -- Main hand
    [17] = 1.0, -- Off hand
    [18] = 0.6, -- Ranged/Relic
}

local SCORE_SLOTS = { 1, 2, 3, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18 }
local ARMOR_SLOTS = {
    [1] = true, [2] = true, [3] = true, [5] = true, [6] = true,
    [7] = true, [8] = true, [9] = true, [10] = true, [15] = true,
}
local SOCKET_STAT_KEYS = {
    "EMPTY_SOCKET_META",
    "EMPTY_SOCKET_RED",
    "EMPTY_SOCKET_YELLOW",
    "EMPTY_SOCKET_BLUE",
    "EMPTY_SOCKET_PRISMATIC",
}

local STAT_KEY_MAP = {
    ITEM_MOD_STRENGTH_SHORT = "ITEM_MOD_STRENGTH_SHORT",
    ITEM_MOD_AGILITY_SHORT = "ITEM_MOD_AGILITY_SHORT",
    ITEM_MOD_STAMINA_SHORT = "ITEM_MOD_STAMINA_SHORT",
    ITEM_MOD_INTELLECT_SHORT = "ITEM_MOD_INTELLECT_SHORT",
    ITEM_MOD_SPIRIT_SHORT = "ITEM_MOD_SPIRIT_SHORT",
    ITEM_MOD_HIT_RATING_SHORT = "ITEM_MOD_HIT_RATING_SHORT",
    ITEM_MOD_CRIT_RATING_SHORT = "ITEM_MOD_CRIT_RATING_SHORT",
    ITEM_MOD_HASTE_RATING_SHORT = "ITEM_MOD_HASTE_RATING_SHORT",
    ITEM_MOD_EXPERTISE_RATING_SHORT = "ITEM_MOD_EXPERTISE_RATING_SHORT",
    ITEM_MOD_DODGE_RATING_SHORT = "ITEM_MOD_DODGE_RATING_SHORT",
    ITEM_MOD_DEFENSE_SKILL_RATING_SHORT = "ITEM_MOD_DEFENSE_SKILL_RATING_SHORT",
    ITEM_MOD_BLOCK_RATING_SHORT = "ITEM_MOD_BLOCK_RATING_SHORT",
    ITEM_MOD_BLOCK_VALUE_SHORT = "ITEM_MOD_BLOCK_VALUE_SHORT",
    ITEM_MOD_ATTACK_POWER_SHORT = "ITEM_MOD_ATTACK_POWER_SHORT",
    ITEM_MOD_RANGED_ATTACK_POWER_SHORT = "ITEM_MOD_RANGED_ATTACK_POWER_SHORT",
    ITEM_MOD_FERAL_ATTACK_POWER_SHORT = "ITEM_MOD_FERAL_ATTACK_POWER_SHORT",
    ITEM_MOD_SPELL_POWER_SHORT = "ITEM_MOD_SPELL_POWER_SHORT",
    ITEM_MOD_HEALING_DONE_SHORT = "ITEM_MOD_HEALING_DONE_SHORT",
    ITEM_MOD_SPELL_HIT_RATING_SHORT = "ITEM_MOD_SPELL_HIT_RATING_SHORT",
    ITEM_MOD_SPELL_CRIT_RATING_SHORT = "ITEM_MOD_SPELL_CRIT_RATING_SHORT",
    ITEM_MOD_SPELL_HASTE_RATING_SHORT = "ITEM_MOD_SPELL_HASTE_RATING_SHORT",
    ITEM_MOD_MANA_REGENERATION_SHORT = "ITEM_MOD_MANA_REGENERATION_SHORT",
    RESILIENCE_RATING = "RESILIENCE_RATING",
}

local function clamp(minV, value, maxV)
    if value < minV then
        return minV
    end
    if value > maxV then
        return maxV
    end
    return value
end

local function parseItemID(itemLink)
    if not itemLink then
        return nil
    end
    local itemID = tonumber(string.match(itemLink, "item:(%d+)"))
    return itemID
end

local function parseItemParts(itemLink)
    local itemString = string.match(itemLink or "", "item:([-%d:]+)")
    if not itemString then
        return nil, {}
    end
    local fields = {}
    for token in string.gmatch(itemString, "([^:]+)") do
        table.insert(fields, tonumber(token) or 0)
    end
    return fields[2], fields
end

local function isTwoHandLink(itemLink)
    if not itemLink then
        return false
    end
    local equipLoc = select(9, GetItemInfo(itemLink))
    return equipLoc == "INVTYPE_2HWEAPON"
end

function addon:InitScoring()
    self.itemEPCache = {}
    self.refEPCache = {}
    self.plateauCache = {}
end

function addon:GetClassData(classToken)
    if not classToken then
        return nil
    end
    return BiScoreData[classToken]
end

function addon:GetProfileKeyForUnit(unit)
    if unit == "player" and BiScoreCharDB and BiScoreCharDB.profileOverride and BiScoreCharDB.profileOverride ~= "auto" then
        return BiScoreCharDB.profileOverride
    end

    local classToken = select(2, UnitClass(unit))
    if not classToken then
        return nil
    end
    local classData = self:GetClassData(classToken)
    if not classData then
        return nil
    end

    local topIndex, topPoints = 1, -1
    local feralDruid = classToken == "DRUID"
    for i = 1, 3 do
        local _, _, points = GetTalentTabInfo(i, false, false, unit)
        if points and points > topPoints then
            topPoints = points
            topIndex = i
        end
    end

    local tabName = GetTalentTabInfo(topIndex, false, false, unit)
    if not tabName then
        return nil
    end

    local profile = tabName
    if feralDruid and tabName == "Feral Combat" then
        local cat = self:GetUnitBiScore(unit, "Feral (Cat)")
        local bear = self:GetUnitBiScore(unit, "Feral (Bear)")
        if cat and bear then
            return (cat.percent >= bear.percent) and "Feral (Cat)" or "Feral (Bear)"
        end
        profile = "Feral (Cat)"
    end

    return profile
end

function addon:GetProfileData(classToken, profileKey, phase)
    local classData = self:GetClassData(classToken)
    if not classData then
        return nil
    end
    local profile = classData[profileKey]
    if not profile then
        return nil
    end
    return profile[phase]
end

function addon:GetItemEP(itemLink, profileData, cacheKey)
    if not itemLink or not profileData then
        return 0
    end
    local key = cacheKey or (itemLink .. "::" .. tostring(profileData))
    local cached = self.itemEPCache[key]
    if cached then
        return cached
    end

    local weights = profileData.weights or {}
    local itemStats = GetItemStats(itemLink) or {}
    local ep = 0

    for statKey, amount in pairs(itemStats) do
        local weightKey = STAT_KEY_MAP[statKey] or statKey
        local weight = weights[weightKey]
        if weight and amount then
            ep = ep + (amount * weight)
        end
    end

    self.itemEPCache[key] = ep
    return ep
end

function addon:GetItemRank(itemID, slotData)
    if not itemID or not slotData or not slotData.ranked then
        return nil
    end
    for rank, rankedID in ipairs(slotData.ranked) do
        if rankedID == itemID then
            return rank
        end
    end
    return nil
end

function addon:GetRankCurveCap(rank, isEnchant)
    local curve = isEnchant and BiScoreDB.enchantRankCapCurve or BiScoreDB.rankCapCurve
    local capFloor = curve and curve.capFloor or 0.85
    local k = curve and curve.k or 0.55
    if rank <= 1 then
        return 1.0
    end
    return capFloor + (1 - capFloor) * (1 / (rank ^ k))
end

function addon:GetPlateauInfo(classToken, profileKey, slotID)
    local cacheKey = classToken .. "::" .. profileKey .. "::" .. tostring(slotID)
    if self.plateauCache[cacheKey] then
        return self.plateauCache[cacheKey]
    end

    local starts = {}
    local previousID = nil
    local currentStart = 1
    for phase = 1, 5 do
        local profileData = self:GetProfileData(classToken, profileKey, phase)
        local slotData = profileData and profileData.slots and profileData.slots[slotID]
        local anchorID = slotData and slotData.ranked and slotData.ranked[1]
        if phase == 1 then
            previousID = anchorID
            currentStart = 1
        elseif anchorID ~= previousID then
            for writePhase = currentStart, phase - 1 do
                starts[writePhase] = { plateauStart = currentStart, nextUpgradePhase = phase }
            end
            currentStart = phase
            previousID = anchorID
        end
    end
    for writePhase = currentStart, 5 do
        starts[writePhase] = { plateauStart = currentStart, nextUpgradePhase = 5 }
    end

    self.plateauCache[cacheKey] = starts
    return starts
end

function addon:GetPhaseScalar(classToken, profileKey, slotID, phase, slotData)
    local boundaries = self:GetPlateauInfo(classToken, profileKey, slotID)
    local info = boundaries[phase] or { plateauStart = phase, nextUpgradePhase = phase }
    local gateFloor = (slotData and slotData.gateFloor) or (profileKey and BiScoreDB.gateFloor) or 0.6

    if info.nextUpgradePhase <= info.plateauStart then
        return 1.0
    end

    local progress = (phase - info.plateauStart) / (info.nextUpgradePhase - info.plateauStart)
    progress = clamp(0, progress, 1)
    return gateFloor + ((1 - gateFloor) * progress)
end

function addon:GetUnlistedSlotMultiplier(slotID, phase)
    local byPhase
    if ARMOR_SLOTS[slotID] then
        byPhase = BiScoreDB and BiScoreDB.unlistedArmorMultByPhase
    else
        byPhase = BiScoreDB and BiScoreDB.unlistedNonArmorMultByPhase
    end
    if byPhase then
        return byPhase[phase] or 1.0
    end
    return 1.0
end

function addon:GetItemSocketCount(itemLink)
    if not itemLink then
        return 0
    end
    local stats = GetItemStats(itemLink) or {}
    local count = 0
    for _, key in ipairs(SOCKET_STAT_KEYS) do
        local value = tonumber(stats[key]) or 0
        count = count + value
    end
    return count
end

function addon:GetSlotFactor(itemLink, slotID, classToken, profileKey, phase, profileData, skipPenalties)
    local slotData = profileData and profileData.slots and profileData.slots[slotID]
    if not slotData or not itemLink then
        return 0, 0, "Empty", nil
    end

    local profileScoring = profileData.scoring or {}
    local floorV = profileScoring.floor or 0.35
    local capV = profileScoring.cap or 1.0

    local itemID = parseItemID(itemLink)
    local refID = slotData.ranked and slotData.ranked[1]
    if not refID then
        return floorV, 0, "Unlisted", itemID
    end

    local refLink = "item:" .. tostring(refID)
    local refCacheKey = string.format("%s:%s:%d:%d", classToken, profileKey, phase, slotID)
    local refEP = self.refEPCache[refCacheKey]
    if not refEP then
        refEP = self:GetItemEP(refLink, profileData, refCacheKey)
        if refEP <= 0 then
            refEP = 1
        end
        self.refEPCache[refCacheKey] = refEP
    end

    local ep = self:GetItemEP(itemLink, profileData)
    local base = clamp(floorV, ep / refEP, capV)

    local rank = self:GetItemRank(itemID, slotData)
    local factor = base
    local label = "Unlisted"

    if rank then
        if rank == 1 then
            factor = 1.0
            label = "BiS Anchor"
        else
            local rankFloor = (slotData.rankFloor and slotData.rankFloor[rank]) or floorV
            local rankCap = (slotData.rankCap and slotData.rankCap[rank]) or self:GetRankCurveCap(rank, false)
            factor = clamp(rankFloor, factor, rankCap)
            label = "Rank " .. tostring(rank)
        end
    end

    if label == "Unlisted" then
        factor = factor * self:GetUnlistedSlotMultiplier(slotID, phase)
    end

    if not skipPenalties then
        local enchantID, parts = parseItemParts(itemLink)
        if enchantID == 0 and BiScoreDB.missingEnchantMultByPhase then
            factor = factor * (BiScoreDB.missingEnchantMultByPhase[phase] or 1.0)
        end
        local filledGems = 0
        for idx = 3, 6 do
            if parts[idx] and parts[idx] ~= 0 then
                filledGems = filledGems + 1
            end
        end
        local socketCount = self:GetItemSocketCount(itemLink)
        if socketCount < filledGems then
            socketCount = filledGems
        end
        local missingGems = socketCount - filledGems
        if missingGems > 0 and BiScoreDB.missingGemMultByPhase then
            local mult = BiScoreDB.missingGemMultByPhase[phase] or 1.0
            factor = factor * (mult ^ missingGems)
        end
    end

    return factor, ep, label, itemID
end

function addon:GetUnitBiScore(unit, forcedProfile)
    if not UnitExists(unit) then
        return nil
    end

    local _, classToken = UnitClass(unit)
    local phase = self:GetCurrentPhase()
    local profileKey = forcedProfile or self:GetProfileKeyForUnit(unit)
    if not classToken or not profileKey then
        return nil
    end

    local profileData = self:GetProfileData(classToken, profileKey, phase)
    if not profileData or not profileData.slots then
        return nil
    end

    local sum = 0
    local sumMax = 0
    local bisSlotCount = 0
    local details = {}
    local skipOffhand = false

    for _, slotID in ipairs(SCORE_SLOTS) do
        if skipOffhand and slotID == 17 then
            skipOffhand = false
        else
            local slotWeight = SLOT_WEIGHTS[slotID] or 0
            local itemLink = GetInventoryItemLink(unit, slotID)
            local slotData = profileData.slots[slotID]
            local phaseScalar = self:GetPhaseScalar(classToken, profileKey, slotID, phase, slotData)
            local effectiveWeight = slotWeight

            if classToken == "HUNTER" and slotID == 18 then
                local rangedMult = (BiScoreDB and BiScoreDB.hunterRangedWeightMult) or 2.0
                effectiveWeight = effectiveWeight * rangedMult
            end

            if slotID == 16 and itemLink and isTwoHandLink(itemLink) then
                if classToken == "HUNTER" then
                    local twoHandMult = (BiScoreDB and BiScoreDB.hunterTwoHandWeightMult) or 0.5
                    effectiveWeight = effectiveWeight * twoHandMult
                else
                    effectiveWeight = slotWeight + (SLOT_WEIGHTS[17] or 0)
                end
                skipOffhand = true
            end

            if slotData then
                local factor, _, label, itemID = self:GetSlotFactor(itemLink, slotID, classToken, profileKey, phase, profileData, false)
                local slotScore = effectiveWeight * phaseScalar * factor
                local maxSlot = effectiveWeight * phaseScalar

                sum = sum + slotScore
                sumMax = sumMax + maxSlot

                if label == "BiS Anchor" then
                    bisSlotCount = bisSlotCount + 1
                end

                details[slotID] = {
                    itemID = itemID,
                    slotScore = slotScore,
                    slotMax = maxSlot,
                    slotWeight = effectiveWeight,
                    factor = factor,
                    phaseScalar = phaseScalar,
                    isBiS = (label == "BiS Anchor"),
                    label = label,
                }
            end
        end
    end

    if sumMax <= 0 then
        return nil
    end

    local phaseTarget = (BiScoreDB.phaseTarget and BiScoreDB.phaseTarget[phase]) or 1800
    local score = math.floor(((sum / sumMax) * phaseTarget) + 0.5)
    local percent = score / phaseTarget

    return {
        score = score,
        maxScore = phaseTarget,
        percent = percent,
        sumScore = sum,
        sumMax = sumMax,
        bisSlotCount = bisSlotCount,
        totalSlots = #SCORE_SLOTS,
        classToken = classToken,
        profileKey = profileKey,
        details = details,
    }
end

function addon:HandleProfileSlash(profileArg)
    if not profileArg then
        self.Print("Current profile override: " .. tostring((BiScoreCharDB and BiScoreCharDB.profileOverride) or "auto"))
        return
    end

    local value = string.lower(profileArg)
    if value == "auto" then
        BiScoreCharDB.profileOverride = "auto"
        self.Print("Profile override set to auto.")
        return
    end

    local _, classToken = UnitClass("player")
    local classData = classToken and BiScoreData[classToken]
    if not classData then
        self.Print("No class data available.")
        return
    end

    for profileKey in pairs(classData) do
        if string.lower(profileKey) == value then
            BiScoreCharDB.profileOverride = profileKey
            self.Print("Profile override set to " .. profileKey)
            return
        end
    end

    self.Print("Unknown profile '" .. tostring(profileArg) .. "'. Use /biscore profile auto to reset.")
end
