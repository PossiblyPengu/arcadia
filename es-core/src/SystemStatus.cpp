//  SPDX-License-Identifier: MIT
//
//  Arcadia Frontend
//  SystemStatus.cpp
//
//  Queries system status information from the operating system.
//  This includes Bluetooth, Wi-Fi, cellular and battery.
//

#include "SystemStatus.h"

#include "Log.h"
#include "Settings.h"
#include "utils/FileSystemUtil.h"
#include "utils/StringUtil.h"

#include <SDL2/SDL_timer.h>

#include <algorithm>

#include <bluetooth/bluetooth.h>
#include <bluetooth/hci.h>
#include <bluetooth/hci_lib.h>




#define DEBUG_SYSTEM_STATUS false

SystemStatus::SystemStatus() noexcept
    : mExitPolling {false}
    , mPollImmediately {false}
    , mHasBluetooth {false}
    , mHasWifi {false}
    , mHasCellular {false}
    , mHasBattery {false}
    , mBatteryCharging {false}
    , mBatteryCapacity {0}
{
    setCheckFlags();

    mPollThread = std::make_unique<std::thread>(&SystemStatus::pollStatus, this);
}

SystemStatus::~SystemStatus()
{
    mExitPolling = true;

    if (mPollThread != nullptr && mPollThread->joinable()) {
        mPollThread->join();
        mPollThread.reset();
    }
}

SystemStatus& SystemStatus::getInstance()
{
    static SystemStatus instance;
    return instance;
}

void SystemStatus::setCheckFlags()
{
    std::unique_lock<std::mutex> statusLock {mStatusMutex};
    mCheckBluetooth = Settings::getInstance()->getBool("SystemStatusBluetooth");
    mCheckWifi = Settings::getInstance()->getBool("SystemStatusWifi");
    mCheckCellular = Settings::getInstance()->getBool("SystemStatusCellular");
    mCheckBattery = Settings::getInstance()->getBool("SystemStatusBattery");

    if (!mCheckBluetooth)
        mHasBluetooth = false;
    if (!mCheckWifi)
        mHasWifi = false;
    if (!mCheckCellular)
        mHasCellular = false;
    if (!mCheckBattery)
        mHasBattery = false;
}

void SystemStatus::setPolling(const bool state)
{

    if (state == false) {
        mExitPolling = true;
        if (mPollThread != nullptr && mPollThread->joinable()) {
            mPollThread->join();
            mPollThread.reset();
        }
    }
    else if (mPollThread == nullptr) {
        mExitPolling = false;
        mPollThread = std::make_unique<std::thread>(&SystemStatus::pollStatus, this);
    }
}

SystemStatus::Status SystemStatus::getStatus(const bool update)
{

    mStatus.hasBluetooth = mHasBluetooth;
    mStatus.hasWifi = mHasWifi;
    mStatus.hasCellular = mHasCellular;
    mStatus.hasBattery = mHasBattery;
    mStatus.batteryCharging = mBatteryCharging;
    mStatus.batteryCapacity = mBatteryCapacity;

    return mStatus;
}

void SystemStatus::pollStatus()
{
    while (!mExitPolling) {
        std::unique_lock<std::mutex> statusLock {mStatusMutex};

        getStatusBluetooth();
        getStatusWifi();
        getStatusCellular();
        getStatusBattery();
        statusLock.unlock();

#if (DEBUG_SYSTEM_STATUS)
        std::string status {"Bluetooth "};
        status.append(mHasBluetooth ? "enabled" : "disabled")
            .append(", Wi-Fi ")
            .append(mHasWifi ? "enabled" : "disabled")
            .append(", cellular ")
            .append(mHasCellular ? "enabled" : "disabled")
            .append(", battery ")
            .append(mHasBattery ? "enabled" : "disabled");
        if (mHasBattery) {
            status.append(" (")
                .append(mBatteryCharging ? "charging" : "not charging")
                .append(" and at ")
                .append(std::to_string(mBatteryCapacity))
                .append("% capacity)");
        }
        LOG(LogDebug) << "SystemStatus::pollStatus(): " << status;
#endif

        int delayValue {0};
        while (!mPollImmediately && !mExitPolling && delayValue < pollingTime) {
            delayValue += 100;
            SDL_Delay(100);
        }

        mPollImmediately = false;
    }
}

void SystemStatus::getStatusBluetooth()
{
    if (!mCheckBluetooth)
        return;

    bool hasBluetooth {false};

    if (hci_get_route(nullptr) != -1)
        hasBluetooth = true;

    mHasBluetooth = hasBluetooth;
}

void SystemStatus::getStatusWifi()
{
    if (!mCheckWifi)
        return;

    bool hasWifi {false};

    const std::string sysEntry {"/sys/class/net"};
    auto entries {Utils::FileSystem::getDirContent(sysEntry, false)};
    for (auto& entry : entries) {
        if (Utils::FileSystem::exists(entry + "/wireless") &&
            Utils::FileSystem::exists(entry + "/operstate")) {
            std::string wifiState;
            std::ifstream fileStream;
            fileStream.open(entry + "/operstate");
            getline(fileStream, wifiState);
            fileStream.close();
            if (Utils::String::toLower(wifiState) == "up")
                hasWifi = true;
        }
    }

    mHasWifi = hasWifi;
}

void SystemStatus::getStatusCellular()
{
    if (!mCheckCellular)
        return;

    bool hasCellular {false};


    mHasCellular = hasCellular;
}

void SystemStatus::getStatusBattery()
{
    if (!mCheckBattery)
        return;

    bool hasBattery {false};
    bool batteryCharging {false};
    int batteryCapacity {0};

    const std::string sysEntry {"/sys/class/power_supply"};
    std::string batteryDir;
    auto entries {Utils::FileSystem::getDirContent(sysEntry, false)};
    if (std::find(entries.cbegin(), entries.cend(), sysEntry + "/BAT0") != entries.cend())
        batteryDir = sysEntry + "/BAT0";
    else if (std::find(entries.cbegin(), entries.cend(), sysEntry + "/BAT1") != entries.cend())
        batteryDir = sysEntry + "/BAT1";
    else if (std::find(entries.cbegin(), entries.cend(), sysEntry + "/battery") != entries.cend())
        batteryDir = sysEntry + "/battery";

    hasBattery = true;

    if (!Utils::FileSystem::exists(batteryDir + "/status"))
        hasBattery = false;
    if (!Utils::FileSystem::exists(batteryDir + "/capacity"))
        hasBattery = false;

    if (hasBattery) {
        std::string batteryStatusValue;
        std::string batteryCapacityValue;
        std::ifstream fileStream;
        fileStream.open(batteryDir + "/status");
        getline(fileStream, batteryStatusValue);
        batteryStatusValue = Utils::String::toLower(batteryStatusValue);
        fileStream.close();

        if (batteryStatusValue != "discharging")
            batteryCharging = true;

        fileStream.open(batteryDir + "/capacity");
        getline(fileStream, batteryCapacityValue);
        fileStream.close();

        batteryCapacity = std::stoi(batteryCapacityValue);
    }

    if (batteryCapacity < 0)
        batteryCapacity = 0;
    if (batteryCapacity > 100)
        batteryCapacity = 100;

    mHasBattery = hasBattery;
    mBatteryCharging = batteryCharging;
    mBatteryCapacity = batteryCapacity;
}
