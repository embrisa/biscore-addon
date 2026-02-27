local addon = BiScore

function addon:InitPhase()
    BiScoreDB = BiScoreDB or {}
    BiScoreCharDB = BiScoreCharDB or {}

    BiScoreDB.phaseTarget = BiScoreDB.phaseTarget or {
        [1] = 1800,
        [2] = 2600,
        [3] = 3200,
        [4] = 3800,
        [5] = 4400,
    }

    BiScoreDB.missingEnchantMultByPhase = BiScoreDB.missingEnchantMultByPhase or {
        [1] = 0.99,
        [2] = 0.98,
        [3] = 0.98,
        [4] = 0.97,
        [5] = 0.97,
    }

    BiScoreDB.missingGemMultByPhase = BiScoreDB.missingGemMultByPhase or {
        [1] = 0.99,
        [2] = 0.99,
        [3] = 0.98,
        [4] = 0.98,
        [5] = 0.98,
    }

    BiScoreDB.rankCapCurve = BiScoreDB.rankCapCurve or { capFloor = 0.85, k = 0.55 }
    BiScoreDB.enchantRankCapCurve = BiScoreDB.enchantRankCapCurve or { capFloor = 0.9, k = 0.65 }
    BiScoreDB.unlistedArmorMultByPhase = BiScoreDB.unlistedArmorMultByPhase or {
        [1] = 0.60,
        [2] = 0.60,
        [3] = 0.60,
        [4] = 0.60,
        [5] = 0.60,
    }
    BiScoreDB.unlistedNonArmorMultByPhase = BiScoreDB.unlistedNonArmorMultByPhase or {
        [1] = 0.85,
        [2] = 0.85,
        [3] = 0.85,
        [4] = 0.85,
        [5] = 0.85,
    }
    BiScoreDB.hunterTwoHandWeightMult = BiScoreDB.hunterTwoHandWeightMult or 0.50
    BiScoreDB.hunterRangedWeightMult = BiScoreDB.hunterRangedWeightMult or 2.00

    if not BiScoreCharDB.phase or BiScoreCharDB.phase < 1 or BiScoreCharDB.phase > 5 then
        BiScoreCharDB.phase = 1
    end
end

function addon:GetCurrentPhase()
    local phase = (BiScoreCharDB and BiScoreCharDB.phase) or 1
    if phase < 1 then
        phase = 1
    elseif phase > 5 then
        phase = 5
    end
    return phase
end

function addon:SetCurrentPhase(phase)
    local num = tonumber(phase)
    if not num or num < 1 or num > 5 then
        return false
    end
    BiScoreCharDB.phase = math.floor(num)
    return true
end

function addon:HandlePhaseSlash(phaseArg)
    if not phaseArg then
        self.Print("Current phase: " .. tostring(self:GetCurrentPhase()))
        return
    end
    if self:SetCurrentPhase(phaseArg) then
        self.Print("Phase set to " .. tostring(self:GetCurrentPhase()))
    else
        self.Print("Usage: /biscore phase <1-5>")
    end
end
