//  SPDX-License-Identifier: MIT
//
//  Arcadia Frontend
//  GuiMsgBox.cpp
//
//  Popup message dialog with a notification text and a choice of one,
//  two or three buttons.
//

#include "guis/GuiMsgBox.h"

#include "utils/LocalizationUtil.h"
#include "utils/StringUtil.h"

#include "components/ButtonComponent.h"
#include "components/ImageComponent.h"
#include "components/MenuComponent.h"

#include <algorithm>

#define HORIZONTAL_PADDING_PX 20.0f
#define VERTICAL_PADDING_MODIFIER 1.225f

// Arcadia (DESIGN.md: never upper case for sentences): English messages are shown in sentence case.
using Utils::Localization::readable;

namespace MessageTone
{
    std::string of(const std::string& text, const std::vector<std::string>& buttons)
    {
        const std::string t {Utils::String::toLower(text)};
        auto has = [&t](const std::vector<std::string>& words) {
            return std::any_of(words.cbegin(), words.cend(),
                               [&t](const std::string& w) { return t.find(w) != std::string::npos; });
        };
        if (has({"couldn't", "could not", "can't", "cannot", "error", "failed", "unable", "invalid", "not found",
                 "missing", "warning", "isn't", "no space"}))
            return "warning";
        // A confirmation whose main (first) choice removes something.
        if (!buttons.empty()) {
            const std::string n {Utils::String::toLower(buttons.front())};
            for (const char* w : {"delete", "remove", "uninstall", "reset", "erase", "overwrite", "clear"}) {
                if (n.find(w) != std::string::npos)
                    return "danger";
            }
        }
        std::string trimmed {t};
        while (!trimmed.empty() && (trimmed.back() == ' ' || trimmed.back() == '\n'))
            trimmed.pop_back();
        if (!trimmed.empty() && trimmed.back() == '?')
            return "question";
        if (has({"is installed", "done", "saved", "updated", "complete", "finished", "added", "success", "ready",
                 "up to date"}))
            return "success";
        return "info";
    }

    std::string badge(const std::string& tone) { return ":/graphics/msgbox/" + tone + ".svg"; }
} // namespace MessageTone

namespace
{
    // A short first sentence becomes the dialog's title, the rest its text ("REALLY DELETE?" is all title).
    std::pair<std::string, std::string> splitHeadline(const std::string& text)
    {
        const size_t limit {90};
        size_t end {std::string::npos};
        for (size_t i {0}; i + 1 < text.size() && i < limit; ++i) {
            const char c {text[i]};
            if ((c == '.' || c == '?' || c == '!' || c == ':') && (text[i + 1] == ' ' || text[i + 1] == '\n')) {
                end = i;
                break;
            }
            if (c == '\n') {
                end = i == 0 ? std::string::npos : i - 1;
                break;
            }
        }
        if (end == std::string::npos)
            return text.size() <= limit && text.find('\n') == std::string::npos ?
                       std::make_pair(text, std::string {}) :
                       std::make_pair(std::string {}, text);
        std::string title {text.substr(0, end + 1)};
        if (title.back() == '.' || title.back() == ':')
            title.pop_back();
        size_t start {end + 1};
        while (start < text.size() && (text[start] == ' ' || text[start] == '\n'))
            ++start;
        return {title, text.substr(start)};
    }
} // namespace

GuiMsgBox::GuiMsgBox(const std::string& text,
                     const std::string& name1,
                     const std::function<void()>& func1,
                     const std::string& name2,
                     const std::function<void()>& func2,
                     const std::string& name3,
                     const std::function<void()>& func3,
                     const std::string& name4,
                     const std::function<void()>& func4,
                     const std::function<void()>& backFunc,
                     const bool disableBackButton,
                     const bool deleteOnButtonPress,
                     const float maxWidthMultiplier)
    : mRenderer {Renderer::getInstance()}
    , mGrid {glm::ivec2 {1, 2}}
    , mBackFunc {backFunc}
    , mDisableBackButton {disableBackButton}
    , mDeleteOnButtonPress {deleteOnButtonPress}
    , mMaxWidthMultiplier {maxWidthMultiplier}
{
    for (const std::string& name : {name1, name2, name3, name4}) {
        if (!name.empty())
            mButtonNames.push_back(name);
    }
    mBadge = std::make_shared<ImageComponent>();
    mTitle = std::make_shared<TextComponent>("", Font::get(FONT_SIZE_MEDIUM * 1.15f, FONT_PATH_TITLE),
                                             mMenuColorTitle, ALIGN_CENTER, ALIGN_CENTER, glm::ivec2 {1, 1});
    // Initially set the text component to wrap by line breaks while maintaining the row lengths.
    // This is the "ideal" size for the text as it's exactly how it's written.
    mMsg = std::make_shared<TextComponent>("", Font::get(FONT_SIZE_MEDIUM), mMenuColorPrimary, ALIGN_CENTER,
                                           ALIGN_CENTER, glm::ivec2 {1, 1});
    setMessage(text);
    mGrid.setEntry(mMsg, glm::ivec2 {0, 0}, false, false);

    // Create the buttons.
    mButtons.push_back(std::make_shared<ButtonComponent>(
        name1, name1, std::bind(&GuiMsgBox::deleteMeAndCall, this, func1)));
    if (!name2.empty())
        mButtons.push_back(std::make_shared<ButtonComponent>(
            name2, name2, std::bind(&GuiMsgBox::deleteMeAndCall, this, func2)));
    if (!name3.empty())
        mButtons.push_back(std::make_shared<ButtonComponent>(
            name3, name3, std::bind(&GuiMsgBox::deleteMeAndCall, this, func3)));
    if (!name4.empty())
        mButtons.push_back(std::make_shared<ButtonComponent>(
            name4, name4, std::bind(&GuiMsgBox::deleteMeAndCall, this, func4)));

    // Put the buttons into a ComponentGrid.
    mButtonGrid = MenuComponent::makeButtonGrid(mButtons);
    mGrid.setEntry(mButtonGrid, glm::ivec2 {0, 1}, true, false, glm::ivec2 {1, 1},
                   GridFlags::BORDER_NONE);

    calculateSize();

    setPosition((mRenderer->getScreenWidth() - mSize.x) / 2.0f,
                (mRenderer->getScreenHeight() - mSize.y) / 2.0f);

    mColors = mMenuColorFrame;
    addChild(&mBackground);
    addChild(mBadge.get());
    addChild(mTitle.get());
    addChild(&mGrid);
}

void GuiMsgBox::setMessage(const std::string& text)
{
    const std::string shown {readable(text)};
    const auto [title, body] = splitHeadline(shown);
    mBadge->setImage(MessageTone::badge(MessageTone::of(text, mButtonNames)));
    const float side {std::round(Font::get(FONT_SIZE_LARGE)->getHeight() * 1.45f)};
    mBadge->setResize(side, side);
    mTitle->setAutoCalcExtent(glm::ivec2 {1, 1});
    mTitle->setText(title);
    mTitle->setVisible(!title.empty());
    mMsg->setAutoCalcExtent(glm::ivec2 {1, 1});
    mMsg->setText(body);
    // A message with a title reads as its explanation: quieter than the title.
    mMsg->setFont(Font::get(title.empty() ? FONT_SIZE_MEDIUM : FONT_SIZE_SMALL));
    mMsg->setColor(title.empty() ? mMenuColorPrimary : mMenuColorSecondary);
}

float GuiMsgBox::headerHeight() const
{
    const float gap {std::round(mRenderer->getScreenHeight() * 0.022f)};
    float h {gap * 1.4f + mBadge->getSize().y + gap * 0.7f};
    if (mTitle->isVisible())
        h += mTitle->getSize().y;
    return std::round(h);
}

void GuiMsgBox::calculateSize()
{
    // Adjust the width relative to the aspect ratio of the screen to make the GUI look coherent
    // regardless of screen type. The 1.778 aspect ratio value is the 16:9 reference.
    const float aspectValue {1.778f / mRenderer->getScreenAspectRatio()};

    if (mMaxWidthMultiplier == 0.0f)
        mMaxWidthMultiplier = mRenderer->getIsVerticalOrientation() ? 0.90f : 0.80f;

    float width {std::floor(glm::clamp(0.60f * aspectValue, 0.60f, mMaxWidthMultiplier) *
                            mRenderer->getScreenWidth())};
    // Arcadia: dialogs get room to breathe (DESIGN.md).
    const float minWidth {
        floorf(glm::clamp(0.38f * aspectValue, 0.10f, 0.55f) * mRenderer->getScreenWidth())};

    // Decide final width.
    if (mMsg->getSize().x < width && mButtonGrid->getSize().x < width) {
        // mMsg and buttons are narrower than width.
        width = std::max(mButtonGrid->getSize().x, mMsg->getSize().x);
        width = std::max(width, minWidth);
    }
    else if (mButtonGrid->getSize().x > width) {
        width = mButtonGrid->getSize().x;
    }

    if (mTitle->isVisible() && mTitle->getSize().x > width)
        width = std::min(mTitle->getSize().x, std::floor(mMaxWidthMultiplier * mRenderer->getScreenWidth()));

    // As the actual rows may be too wide to fit we change to wrapping by our component width
    // while allowing expansion vertically. Setting the width will update the text cache.
    mMsg->setAutoCalcExtent(glm::vec2 {0, 1});
    mMsg->setSize(width, 0.0f);
    mTitle->setAutoCalcExtent(glm::vec2 {0, 1});
    mTitle->setSize(width, 0.0f);

    // (A title with nothing under it needs only a little room before the buttons.)
    const float msgHeight {mMsg->getValue().empty() ?
                               std::round(mRenderer->getScreenHeight() * 0.025f) :
                               std::max(Font::get(FONT_SIZE_SMALL)->getHeight() * 1.6f,
                                        mMsg->getSize().y * VERTICAL_PADDING_MODIFIER * 1.15f)};
    setSize(std::round(width + std::ceil(HORIZONTAL_PADDING_PX * 2.0f *
                                         mRenderer->getScreenWidthModifier())),
            std::round(headerHeight() + msgHeight + mButtonGrid->getSize().y +
                       mRenderer->getScreenHeight() * 0.03f));
}

void GuiMsgBox::changeText(const std::string& newText)
{
    setMessage(newText);
    calculateSize();
}

bool GuiMsgBox::input(InputConfig* config, Input input)
{
    if (!mDisableBackButton && config->isMappedTo("b", input) && input.value != 0) {
        if (mBackFunc)
            mBackFunc();
        delete this;
        return true;
    }

    return GuiComponent::input(config, input);
}

void GuiMsgBox::update(int deltaTime)
{
    // Arcadia: follow a change of colours made while this was open underneath (the first-start screen stays up
    // under Settings); its buttons already do, the card and the words didn't.
    if (mColors != mMenuColorFrame) {
        mColors = mMenuColorFrame;
        mBackground.setFrameColor(mMenuColorFrame);
        mTitle->setColor(mMenuColorTitle);
        mMsg->setColor(mTitle->isVisible() ? mMenuColorSecondary : mMenuColorPrimary);
    }
    GuiComponent::update(deltaTime);
}

void GuiMsgBox::onSizeChanged()
{
    // The heading on top (badge, then title), the message and the buttons below it.
    const float gap {std::round(mRenderer->getScreenHeight() * 0.022f)};
    const float header {headerHeight()};
    mBadge->setPosition(std::round((mSize.x - mBadge->getSize().x) / 2.0f), std::round(gap * 1.4f));
    const float pad {std::ceil(HORIZONTAL_PADDING_PX * Renderer::getScreenWidthModifier())};
    mTitle->setSize(mSize.x - pad * 2.0f, mTitle->getSize().y);
    mTitle->setPosition(pad, std::round(gap * 1.4f + mBadge->getSize().y + gap * 0.7f));
    mGrid.setPosition(0.0f, header);
    mGrid.setSize(mSize.x, mSize.y - header);
    mGrid.setRowHeightPerc(
        1, (mButtonGrid->getSize().y + mRenderer->getScreenHeight() * 0.03f) / (mSize.y - header));

    mMsg->setSize(mSize.x -
                      std::ceil(HORIZONTAL_PADDING_PX * 2.0f * Renderer::getScreenWidthModifier()),
                  mGrid.getRowHeight(0));
    mGrid.onSizeChanged();

    mBackground.fitTo(mSize);
}

void GuiMsgBox::deleteMeAndCall(const std::function<void()>& func)
{
    auto funcCopy = func;

    if (mDeleteOnButtonPress)
        delete this;

    if (funcCopy)
        funcCopy();
}

std::vector<HelpPrompt> GuiMsgBox::getHelpPrompts()
{
    std::vector<HelpPrompt> prompts {mGrid.getHelpPrompts()};

    if (!mDisableBackButton)
        prompts.push_back(HelpPrompt("b", _("back")));

    return prompts;
}
