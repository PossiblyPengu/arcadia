//  SPDX-License-Identifier: MIT
//
//  Arcadia Frontend
//  GuiInfoPopup.cpp
//
//  Popup window used for user notifications.
//

#include "guis/GuiInfoPopup.h"

#include "components/ImageComponent.h"
#include "components/TextComponent.h"
#include "guis/GuiMsgBox.h"
#include "utils/LocalizationUtil.h"
#include "utils/StringUtil.h"

#include <SDL2/SDL_timer.h>

#include <sstream>

// Arcadia: a notification is a card at the top of the screen with a badge that says what it is about (done, a
// problem, information) beside the message, in sentence case. It slides down a little as it fades in.
GuiInfoPopup::GuiInfoPopup(std::string message, int duration)
    : mRenderer {Renderer::getInstance()}
    , mMessage {message}
    , mDuration {duration}
    , mAlpha {1.0f}
    , mRunning {true}
{
    mBackground = new BackgroundComponent(glm::vec2 {24.0f, 24.0f});
    const float maxWidth {Renderer::getScreenWidth() * 0.7f};
    const float padX {std::round(Renderer::getScreenWidth() * 0.016f)};
    const float padY {std::round(Renderer::getScreenHeight() * 0.018f)};

    const std::shared_ptr<Font> font {Font::get(FONT_SIZE_SMALL)};
    mText = new TextComponent("", font, mMenuColorPrimary, ALIGN_LEFT, ALIGN_CENTER);
    mText->setSize(0.0f, 0.0f); // (grow to fit the words, then wrap if too wide)
    // The badge says it's a problem, so the words needn't start with "Error:".
    std::string shown {Utils::Localization::readable(message)};
    if (shown.rfind("Error: ", 0) == 0)
        shown = Utils::String::toUpper(shown.substr(7, 1)) + shown.substr(8);
    mText->setText(shown);

    const float side {std::round(font->getHeight() * 1.5f)};
    mBadge = new ImageComponent();
    mBadge->setImage(MessageTone::badge(MessageTone::of(message)));
    mBadge->setResize(side, side);

    const float textRoom {maxWidth - side - padX * 3.0f};
    // As wide as its longest line (a short message on two lines keeps its line break), wrapped if wider than the
    // room there is.
    float longest {0.0f};
    std::istringstream lines {shown};
    for (std::string line; std::getline(lines, line);)
        longest = std::max(longest, font->sizeText(line).x);
    if (shown.find('\n') != std::string::npos || mText->getSize().x > textRoom) {
        mText->setAutoCalcExtent(glm::ivec2 {0, 1});
        mText->setSize(std::min(std::ceil(longest) + 2.0f, textRoom), 0.0f);
    }
    const float textHeight {std::min(mText->getSize().y, Renderer::getScreenHeight() * 0.2f)};
    mText->setSize(mText->getSize().x, textHeight);

    mSize = {padX + side + padX * 0.8f + mText->getSize().x + padX * 1.2f,
             std::max(side, textHeight) + padY * 2.0f};
    mBadge->setPosition(padX, std::round((mSize.y - side) / 2.0f));
    mText->setPosition(padX + side + padX * 0.8f, std::round((mSize.y - textHeight) / 2.0f));

    mRestY = std::round(Renderer::getScreenHeight() * 0.025f);
    setPosition(std::round(Renderer::getScreenWidth() * 0.5f - mSize.x * 0.5f), mRestY, 0);

    mBackground->fitTo(mSize);
    addChild(mBackground);
    addChild(mBadge);
    addChild(mText);

    // We only initialize the actual time when we first start to render.
    mStartTime = 0;
}

GuiInfoPopup::~GuiInfoPopup()
{
    delete mText;
    delete mBadge;
    delete mBackground;
}

void GuiInfoPopup::render(const glm::mat4& /*parentTrans*/)
{
    // We use getIdentity() as we want to render on a specific window position, not on the view.
    const glm::mat4 trans {getTransform() * Renderer::getIdentity()};
    if (mRunning && updateState()) {
        // If we're still supposed to be rendering it.
        mRenderer->setMatrix(trans);
        renderChildren(trans);
    }
}

bool GuiInfoPopup::updateState()
{
    const int curTime {static_cast<int>(SDL_GetTicks())};

    // We only initialize the actual time when we first start to render.
    if (mStartTime == 0)
        mStartTime = curTime;

    // Compute fade-in effect.
    if (curTime - mStartTime > mDuration) {
        // We're past the popup duration, no need to render.
        mRunning = false;
        return false;
    }
    else if (curTime < mStartTime) {
        // If SDL reset.
        mRunning = false;
        return false;
    }
    else if (curTime - mStartTime <= 500) {
        mAlpha = static_cast<float>((curTime - mStartTime) / 500.0f);
    }
    else if (curTime - mStartTime < mDuration - 500) {
        mAlpha = 1.0f;
    }
    else {
        mAlpha = static_cast<float>((-(curTime - mStartTime - mDuration)) / 500.0f);
    }
    mText->setOpacity(mAlpha);
    mBadge->setOpacity(mAlpha);
    // Slide down into place as it appears (and back up as it goes).
    const float slide {(1.0f - mAlpha) * Renderer::getScreenHeight() * 0.03f};
    setPosition(getPosition().x, mRestY - slide, 0.0f);

    // Apply fade-in effect to popup frame.
    mBackground->setFrameColor((mMenuColorFrame & 0xFFFFFF00) |
                               static_cast<unsigned char>(mAlpha * 255.0f));
    return true;
}
