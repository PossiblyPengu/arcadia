//  SPDX-License-Identifier: MIT
//
//  Arcadia Frontend
//  GuiInfoPopup.h
//
//  Popup window used for user notifications.
//

#ifndef ES_APP_GUIS_GUI_INFO_POPUP_H
#define ES_APP_GUIS_GUI_INFO_POPUP_H

#include "GuiComponent.h"
#include "components/BackgroundComponent.h"
#include "renderers/Renderer.h"

class BackgroundComponent;
class ImageComponent;
class TextComponent;

class GuiInfoPopup : public GuiComponent
{
public:
    GuiInfoPopup(std::string message, int duration);
    ~GuiInfoPopup();

    void render(const glm::mat4& parentTrans);
    void stop() { mRunning = false; }
    bool isRunning() { return mRunning; }

private:
    bool updateState();

    Renderer* mRenderer;
    BackgroundComponent* mBackground;
    ImageComponent* mBadge;
    TextComponent* mText;
    float mRestY; // where it settles; it slides down to there as it fades in

    std::string mMessage;
    int mDuration;
    float mAlpha;
    int mStartTime;
    bool mRunning;
};

#endif // ES_APP_GUIS_GUI_INFO_POPUP_H
