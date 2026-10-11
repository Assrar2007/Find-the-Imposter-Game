"""Headless Chromium smoke tests. Uses set_content because the evaluation sandbox blocks page navigation.
Run: python tests/smoke_browser.py   (requires playwright and a Chromium executable)
"""
from pathlib import Path
from playwright.sync_api import sync_playwright

HTML = Path(__file__).resolve().parent.parent.joinpath('index.html').read_text(encoding='utf-8')
RESULTS=[]


def newpage(browser, width=390):
    page = browser.new_page(viewport={'width': width, 'height': 844}, has_touch=True)
    errors=[]
    page.on('pageerror', lambda exc: errors.append(str(exc)))
    page.set_content(HTML, wait_until='domcontentloaded')
    page.set_default_timeout(6000)
    return page,errors


def click(page, action, value=None):
    selector=f'[data-action="{action}"]'
    if value is not None: selector+=f'[data-value="{value}"]'
    page.locator(selector).first.click()


def snapshot(page):
    return page.evaluate("""() => ({screen:state.screen, word:state.round?.word, imposters:state.round?.imposters, alive:state.round?.alive, voter:state.round?.ballot?.voters[state.round?.ballot?.index], members:state.setup.players.map(x=>x.id), scores:state.scores})""")


def create_game(page, count, imposters=1):
    click(page, 'play')
    for _ in range(count - 4):
        click(page, 'increasePlayers')
    for _ in range(4 - count):
        click(page, 'decreasePlayers')
    if imposters==2: click(page,'imposterCount',2)
    click(page, 'timerSeconds',0)
    assert page.locator('[data-action="start"]').is_enabled()
    click(page, 'start')


def reveal_all(page, count):
    for i in range(count):
        assert snapshot(page)['screen']=='reveal'
        info=snapshot(page)
        assert info['word'] not in page.locator('main').inner_text(), 'Secret leaks in cover'
        # Disable anti-double-tap guard during automation; actual user delay remains in app.
        page.evaluate('clickGuard=-1000')
        click(page, 'openReveal')
        assert 'HOLD TO' in page.locator('main').inner_text()
        click(page,'tapReveal')
        content=page.locator('.reveal-panel').inner_text()
        if info['members'][i] in info['imposters']:
            assert 'IMPOSTER' in content
            assert info['word'] not in content
        else:
            assert info['word'].casefold() in content.casefold()
        click(page,'tapReveal')
        assert info['word'] not in page.locator('main').inner_text()
        page.evaluate('clickGuard=-1000')
        click(page,'nextReveal')
    assert 'Everyone is' in page.locator('main').inner_text()
    click(page,'beginClues')
    for _ in range(count):click(page,'nextSpeaker')
    assert snapshot(page)['screen']=='discussion'
    click(page,'goVote')


def vote_cycle(page, choice):
    for _ in range(16):
        if snapshot(page)['screen']!='voting':break
        page.evaluate('clickGuard=-1000')
        click(page,'openBallot')
        b=page.evaluate('({voter:state.round.ballot.voters[state.round.ballot.index], candidates:state.round.ballot.candidates})')
        target=choice(b)
        assert target != b['voter']
        assert target in b['candidates']
        # Explicitly confirm no self-vote shown.
        assert page.locator(f'[data-action="selectVote"][data-value="{b["voter"]}"]').count()==0
        click(page,'selectVote',target)
        page.evaluate('clickGuard=-1000')
        click(page,'confirmVote')


def test_crew(browser):
    page,errors=newpage(browser)
    create_game(page,4)
    info=snapshot(page)
    reveal_all(page,4)
    imp=info['imposters'][0]
    vote_cycle(page,lambda b:imp if b['voter']!=imp else next(x for x in b['candidates'] if x!=imp))
    assert snapshot(page)['screen']=='tally'
    click(page,'continueTally')
    assert snapshot(page)['screen']=='guess'
    assert info['word'] not in page.locator('main').inner_text(), 'Guess leaked in cover'
    page.evaluate('clickGuard=-1000')
    click(page,'openGuess')
    assert page.locator('[data-action="selectGuess"]').count()==6
    wrong=page.evaluate('state.round.guessChoices.findIndex(w=>w!==state.round.word)')
    page.locator(f'[data-action="selectGuess"][data-index="{wrong}"]').click()
    page.evaluate('clickGuard=-1000')
    click(page,'confirmGuess')
    assert snapshot(page)['screen']=='result'
    assert page.locator('main').inner_text().find('The truth')>=0
    scores=snapshot(page)['scores']
    assert scores[imp]==0 and all(scores[x]==1 for x in info['members'] if x!=imp)
    click(page,'scoreboard')
    assert snapshot(page)['screen']=='scoreboard'
    click(page,'nextRound')
    assert snapshot(page)['word'] != info['word'], 'Word repeated immediately'
    assert not errors,errors
    page.close()
    RESULTS.append('4 players: private reveal, crew capture, wrong imposter guess, scoring, repeat protection — PASS')


def test_survivor(browser):
    page,errors=newpage(browser,width=360)
    # Exercise actual source rule transitions without dozens of slow scroll-to-click interactions.
    page.evaluate("""() => {
      state.setup.players=Array.from({length:8},(_,i)=>({id:`p${i+1}`,name:`Player ${i+1}`}));
      state.setup.imposterCount=2; startGame(); beginBallot();
      const innocent=state.round.alive.find(x=>!state.round.imposters.includes(x));
      state.round.ballot.votes=Object.fromEntries(state.round.alive.map(id=>[id,id===innocent?state.round.alive.find(x=>x!==id):innocent]));
      resolveBallot();
    }""")
    assert snapshot(page)['screen']=='tally'
    page.evaluate("""() => {
      continueTally();
      const caught=state.round.imposters[0];
      state.round.ballot.votes=Object.fromEntries(state.round.alive.map(id=>[id,id===caught?state.round.alive.find(x=>x!==id):caught]));
      resolveBallot(); continueTally();
    }""")
    info=snapshot(page)
    assert info['screen']=='result'
    assert 'Deception' in page.locator('main').inner_text()
    assert all(info['scores'][x]==3 for x in info['imposters'])
    assert all(info['scores'][x]==0 for x in info['members'] if x not in info['imposters'])
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    assert not errors, errors
    page.close()
    RESULTS.append('8 players, 2 imposters: wrong elimination, one survives, +3 scores — PASS (browser logic)')


def test_deadlock(browser):
    page,errors=newpage(browser,width=360)
    page.evaluate("""() => {
       state.setup.players=state.setup.players.slice(0,3);startGame();beginBallot();
       state.round.ballot.votes={p1:'p2',p2:'p3',p3:'p1'};resolveBallot();
    }""")
    assert snapshot(page)['screen']=='tally'
    assert 'deadlock' in page.locator('main').inner_text()
    page.evaluate("""() => {
       continueTally();
       state.round.ballot.votes={p1:'p2',p2:'p3',p3:'p1'};
       resolveBallot();
    }""")
    assert snapshot(page)['screen']=='result'
    assert 'Deception' in page.locator('main').inner_text()
    assert not errors, errors
    page.close()
    RESULTS.append('3 players: tied ballot, runoff tie => imposter victory — PASS (browser logic)')


def test_layout(browser):
    page,errors=newpage(browser,width=360)
    click(page,'play')
    for _ in range(8):click(page,'increasePlayers')
    assert page.locator('[data-name-index]').count()==12
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    click(page,'imposterCount',2)
    click(page,'timerSeconds',0)
    click(page,'start')
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    # Modal and keyboard behavior
    page.evaluate('clickGuard=-1000')
    click(page,'quit')
    assert page.locator('[role="dialog"]').count()==1
    page.keyboard.press('Escape')
    assert page.locator('[role="dialog"]').count()==0
    assert not errors,errors
    page.close()
    RESULTS.append('360px, 12 players: no horizontal overflow, modal escape — PASS')


def test_word_guess_win_and_controls(browser):
    page,errors=newpage(browser,width=390)
    page.evaluate("""() => {startGame();const target=state.round.imposters[0];beginBallot();state.round.ballot.votes=Object.fromEntries(state.round.alive.map(id=>[id,id===target?state.round.alive.find(x=>x!==id):target]));resolveBallot();continueTally()}""")
    assert snapshot(page)['screen']=='guess'
    page.evaluate('clickGuard=-1000')
    click(page,'openGuess')
    assert page.locator('[data-action="selectGuess"]').count()==6
    selected=page.evaluate('state.round.guessChoices.indexOf(state.round.word)')
    page.locator(f'[data-action="selectGuess"][data-index="{selected}"]').click()
    page.evaluate('clickGuard=-1000')
    click(page,'confirmGuess')
    info=snapshot(page)
    assert info['screen']=='result'
    assert all(info['scores'][id]==2 for id in info['imposters'])
    assert all(info['scores'][id]==0 for id in info['members'] if id not in info['imposters'])
    assert not errors,errors
    page.close()
    RESULTS.append('Captured imposter guesses correct word => reversal and +2 to imposter — PASS')


def test_reveal_and_timer(browser):
    page,errors=newpage(browser,width=390)
    create_game(page,4)
    page.evaluate('clickGuard=-1000')
    click(page,'openReveal')
    card=page.locator('[data-hold="role"]')
    # A pointer-down reveals; a pointer-up hides. Keyboard Enter toggles without holding.
    card.dispatch_event('pointerdown',{'pointerId':1,'button':0})
    assert page.evaluate('state.round.revealed') is True
    card.dispatch_event('pointerup',{'pointerId':1,'button':0})
    assert page.evaluate('state.round.revealed') is False
    card.focus();page.keyboard.press('Enter')
    assert page.evaluate('state.round.revealed') is True
    page.evaluate('hideRole()')
    assert page.evaluate('state.round.revealed') is False
    # Clock state and expiry transition, independent of actual timer waiting.
    page.evaluate('state.setup.timerSeconds=60;beginDiscussion()')
    assert snapshot(page)['screen']=='discussion'
    click(page,'toggleClock')
    assert page.evaluate('state.clock.running') is False
    click(page,'toggleClock')
    assert page.evaluate('state.clock.running') is True
    page.evaluate('state.clock.deadline=Date.now()-1000;paintClock()')
    assert snapshot(page)['screen']=='voting'
    assert not errors,errors
    page.close()
    RESULTS.append('Reveal hold/release, keyboard toggle; timer pause/resume/expiry — PASS')


if __name__=='__main__':
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
        for t in (test_crew,test_survivor,test_deadlock,test_layout,test_word_guess_win_and_controls,test_reveal_and_timer):
            t(browser)
        browser.close()
    print('\n'.join(RESULTS))
