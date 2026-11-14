//  SPDX-License-Identifier: MIT
//
//  Arcadia
//  GuiFreeGames.h
//
//  The Free games screen in Setup: homebrew and freeware from Homebrew Hub and libretro's library, by console. Pick a
//  console, then a game: A shows what it is, and Get downloads it into the right ROM folder with its name, description
//  and picture. Leaving after getting something rescans the ROM folders, so the new games are there. The work is done
//  by deck/lib/freegames.py through deck/tools/free-games.sh.
//

#ifndef ES_APP_GUIS_GUI_FREE_GAMES_H
#define ES_APP_GUIS_GUI_FREE_GAMES_H

#include "GuiComponent.h"
#include "components/BackgroundComponent.h"
#include "components/ComponentList.h"
#include "components/TextComponent.h"

#include <atomic>
#include <functional>
#include <memory>
#include <mutex>
#include <thread>

class GuiFreeGames : public GuiComponent
{
public:
    GuiFreeGames(const std::string& toolsDirectory, std::function<void()> onClose = nullptr);
    ~GuiFreeGames();

    void update(int deltaTime) override;
    void render(const glm::mat4& parentTrans) override;
    bool input(InputConfig* config, Input input) override;
    std::vector<HelpPrompt> getHelpPrompts() override;

private:
    struct Game {
        std::string id;
        std::string system;
        std::string console;
        std::string title;
        std::string by;
        bool installed;
        std::string blurb;
    };
    // What the list's thread reads. Shared with it, so leaving early can't leave it writing into freed memory.
    struct Shared {
        std::mutex mutex;
        std::vector<Game> games;
        std::string error;
        std::atomic<bool> done {false};
    };

    void layout();
    void readList(bool refresh = false);
    void showConsoles();
    void newList();
    void showGames(const std::string system);
    void choose(const Game& game);
    void get(const Game& game);
    void back();
    void finish();
    int installedCount() const;

    Renderer* mRenderer;
    std::string mToolsDirectory;
    std::function<void()> mOnClose;
    BackgroundComponent mCard;
    TextComponent mHeadline;
    TextComponent mSubline;
    std::shared_ptr<ComponentList> mList;
    std::vector<std::shared_ptr<ComponentList>> mRetiredLists;

    std::shared_ptr<Shared> mShared;
    std::vector<Game> mGames;
    std::string mSystem; // the console whose games are shown ("" = the consoles)
    std::string mLastGot; // the console of the last game got (shown when leaving)
    int mConsoleCursor;
    int mInstalledAtStart;
    bool mLoaded;
    bool mGotSomething; // a game was added: rescan when leaving
};

#endif // ES_APP_GUIS_GUI_FREE_GAMES_H
