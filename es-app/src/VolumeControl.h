//  SPDX-License-Identifier: MIT
//
//  Arcadia Frontend
//  VolumeControl.h
//
//  Controls system audio volume.
//

#ifndef ES_APP_VOLUME_CONTROL_H
#define ES_APP_VOLUME_CONTROL_H

#include <memory>

#include <alsa/asoundlib.h>
#include <fcntl.h>
#include <unistd.h>

class VolumeControl
{
public:
    VolumeControl();
    ~VolumeControl();

    void init();
    void deinit();

    int getVolume() const;
    void setVolume(int volume);

    static std::string mixerName;
    static std::string mixerCard;
    int mixerIndex;
    snd_mixer_t* mixerHandle;
    snd_mixer_elem_t* mixerElem;
    snd_mixer_selem_id_t* mixerSelemId;
};

#endif // ES_APP_VOLUME_CONTROL_H
