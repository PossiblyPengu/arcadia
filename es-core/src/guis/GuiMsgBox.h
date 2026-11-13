//  SPDX-License-Identifier: MIT
//
//  Arcadia Frontend
//  GuiMsgBox.h
//
//  Popup message dialog with a notification text and a choice of one,
//  two or three buttons.
//

#ifndef ES_CORE_GUIS_GUI_MSG_BOX_H
#define ES_CORE_GUIS_GUI_MSG_BOX_H

#include "GuiComponent.h"
#include "components/BackgroundComponent.h"
#include "components/ComponentGrid.h"
#include "utils/LocalizationUtil.h"

class ButtonComponent;
class ImageComponent;
class TextComponent;

namespace MessageTone
{
    // What a message is about, from its words and its buttons: "warning" (something went wrong), "danger" (a choice
    // that removes something), "question", "success" or "info". Dialogs and notifications show it as a pastel badge.
    std::string of(const std::string& text, const std::vector<std::string>& buttons = {});
    // The badge for a tone (":/graphics/msgbox/<tone>.svg").
    std::string badge(const std::string& tone);
} // namespace MessageTone

class GuiMsgBox : public GuiComponent
{
public:
    GuiMsgBox(const std::string& text,
              const std::string& name1 = _("OK"),
              const std::function<void()>& func1 = nullptr,
              const std::string& name2 = "",
              const std::function<void()>& func2 = nullptr,
              const std::string& name3 = "",
              const std::function<void()>& func3 = nullptr,
              const std::string& name4 = "",
              const std::function<void()>& func4 = nullptr,
              const std::function<void()>& backFunc = nullptr,
              const bool disableBackButton = false,
              const bool deleteOnButtonPress = true,
              const float maxWidthMultiplier = 0.0f);

    void calculateSize();

    void changeText(const std::string& newText);

    bool input(InputConfig* config, Input input) override;
    void update(int deltaTime) override;
    void onSizeChanged() override;

    std::vector<HelpPrompt> getHelpPrompts() override;

private:
    void deleteMeAndCall(const std::function<void()>& func);
    void setMessage(const std::string& text);
    float headerHeight() const;

    Renderer* mRenderer;
    BackgroundComponent mBackground;
    ComponentGrid mGrid;

    std::shared_ptr<TextComponent> mMsg;
    // The heading: a badge that says what the message is about, and its first sentence as a title.
    std::shared_ptr<ImageComponent> mBadge;
    std::shared_ptr<TextComponent> mTitle;
    std::vector<std::string> mButtonNames;
    unsigned int mColors; // the frame colour it was drawn with (see update())
    std::vector<std::shared_ptr<ButtonComponent>> mButtons;
    std::shared_ptr<ComponentGrid> mButtonGrid;
    const std::function<void()> mBackFunc;
    bool mDisableBackButton;
    bool mDeleteOnButtonPress;
    float mMaxWidthMultiplier;
};

#endif // ES_CORE_GUIS_GUI_MSG_BOX_H
