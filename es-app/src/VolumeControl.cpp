//  SPDX-License-Identifier: MIT
//
//  Arcadia Frontend
//  VolumeControl.cpp
//
//  Controls system audio volume.
//

#include "VolumeControl.h"

#include "Log.h"
#include "utils/MathUtil.h"


std::string VolumeControl::mixerName = "Master";
std::string VolumeControl::mixerCard = "default";

VolumeControl::VolumeControl()
// clang-format off
    : mixerIndex {0}
    , mixerHandle {nullptr}
    , mixerElem {nullptr}
    , mixerSelemId {nullptr}
// clang-format on
{
    init();
}

VolumeControl::~VolumeControl()
{
    deinit();
    snd_config_update_free_global();
}

void VolumeControl::init()
{
    // Initialize audio mixer interface.

    // Try to open mixer device.
    if (mixerHandle == nullptr) {
        snd_mixer_selem_id_alloca(&mixerSelemId);
        // Sets simple-mixer index and name.
        snd_mixer_selem_id_set_index(mixerSelemId, mixerIndex);
        snd_mixer_selem_id_set_name(mixerSelemId, mixerName.c_str());
        if (snd_mixer_open(&mixerHandle, 0) >= 0) {
            LOG(LogDebug) << "VolumeControl::init(): Opened ALSA mixer";
            if (snd_mixer_attach(mixerHandle, mixerCard.c_str()) >= 0) {
                LOG(LogDebug) << "VolumeControl::init(): Attached to default card";
                if (snd_mixer_selem_register(mixerHandle, nullptr, nullptr) >= 0) {
                    LOG(LogDebug) << "VolumeControl::init(): Registered simple element class";
                    if (snd_mixer_load(mixerHandle) >= 0) {
                        LOG(LogDebug) << "VolumeControl::init(): Loaded mixer elements";
                        // Find elements.
                        mixerElem = snd_mixer_find_selem(mixerHandle, mixerSelemId);
                        if (mixerElem != nullptr) {
                            LOG(LogDebug) << "VolumeControl::init(): Mixer initialized";
                        }
                        else {
                            LOG(LogError)
                                << "VolumeControl::init(): Failed to find mixer elements!";
                            snd_mixer_close(mixerHandle);
                            mixerHandle = nullptr;
                        }
                    }
                    else {
                        LOG(LogError) << "VolumeControl::init(): Failed to load mixer elements!";
                        snd_mixer_close(mixerHandle);
                        mixerHandle = nullptr;
                    }
                }
                else {
                    LOG(LogError)
                        << "VolumeControl::init(): Failed to register simple element class!";
                    snd_mixer_close(mixerHandle);
                    mixerHandle = nullptr;
                }
            }
            else {
                LOG(LogError) << "VolumeControl::init(): Failed to attach to default card!";
                snd_mixer_close(mixerHandle);
                mixerHandle = nullptr;
            }
        }
        else {
            LOG(LogError) << "VolumeControl::init(): Failed to open ALSA mixer!";
        }
    }
}

void VolumeControl::deinit()
{
    // Deinitialize audio mixer interface.

    if (mixerHandle != nullptr) {
        snd_mixer_detach(mixerHandle, mixerCard.c_str());
        snd_mixer_free(mixerHandle);
        snd_mixer_close(mixerHandle);
        mixerHandle = nullptr;
        mixerElem = nullptr;
    }
}

int VolumeControl::getVolume() const
{
    int volume = 0;

    if (mixerElem != nullptr) {
        // Get volume range.
        long minVolume;
        long maxVolume;
        if (snd_mixer_selem_get_playback_volume_range(mixerElem, &minVolume, &maxVolume) == 0) {
            long rawVolume;
            if (snd_mixer_selem_get_playback_volume(mixerElem, SND_MIXER_SCHN_MONO, &rawVolume) ==
                0) {
                // Bring into range 0-100.
                rawVolume -= minVolume;
                if (rawVolume > 0)
                    volume = (rawVolume * 100.0) / (maxVolume - minVolume) + 0.5;
            }
            else {
                LOG(LogError) << "VolumeControl::getVolume(): Failed to get mixer volume";
            }
        }
        else {
            LOG(LogError) << "VolumeControl::getVolume(): Failed to get volume range";
        }
    }

    volume = glm::clamp(volume, 0, 100);
    return volume;
}

void VolumeControl::setVolume(int volume)
{
    volume = glm::clamp(volume, 0, 100);

    if (mixerElem != nullptr) {
        // Get volume range.
        long minVolume;
        long maxVolume;
        if (snd_mixer_selem_get_playback_volume_range(mixerElem, &minVolume, &maxVolume) == 0) {
            // Bring into minVolume-maxVolume range and set.
            long rawVolume = (volume * (maxVolume - minVolume) / 100) + minVolume;
            if (snd_mixer_selem_set_playback_volume(mixerElem, SND_MIXER_SCHN_FRONT_LEFT,
                                                    rawVolume) < 0 ||
                snd_mixer_selem_set_playback_volume(mixerElem, SND_MIXER_SCHN_FRONT_RIGHT,
                                                    rawVolume) < 0) {
                LOG(LogError) << "VolumeControl::getVolume(): Failed to set mixer volume";
            }
        }
        else {
            LOG(LogError) << "VolumeControl::getVolume(): Failed to get volume range";
        }
    }
}
